"""Command line of MonitorEO:

    monitoreo list [--sensor S] [--text T]           variables of the catalog
    monitoreo info VARIABLE [--sensor S]             everything about a variable
    monitoreo classes VARIABLE [--sensor S] [--text T] [--limit N] [--lang es]
                                                     the classes of a categorical layer (ECOREGION, BIOME of sensor
                                                     RESOLVE): code, name, colour and biome (without Earth Engine)
    monitoreo parks TEXT [--ramsar]                  protected areas of WDPA with TEXT in their name
    monitoreo units TEXT [--level 1|2|3] [--country ISO3]   administrative units of FAO GAUL 2025 by name; level 3:
                                                     the municipalities of Spain, of the IGN (without Earth Engine)
    monitoreo seas TEXT                              oceans and seas (the sea areas of the IHO, Marine Regions) by
                                                     name, with their MRGID (without Earth Engine)
    monitoreo series VARIABLE --sensor S --region JSON --start D --end D [--step monthly] [--csv F] [--png F] [--doy]
    monitoreo series VARIABLE ... --doy [--interannual median] [--other-variable V [--other-sensor S]] [--ylim -1 1]
                     [--other-ylim -1 1]             the seasonal profile by day of the year: the metric between the
                                                     years of the values of each step of the year (each month, 16 days
                                                     or day), of one variable or of two on two y axes (e.g. NDSI and
                                                     NDVI)
    monitoreo recovery VARIABLE --sensor S --region JSON --start D --end D --event D [--affected A --control C | --ring]
                                                     severity and recovery after a disturbance (Marcos et al. 2023)
    monitoreo recovery-map VARIABLE --sensor S --region JSON --start D --end D --event D [--season MM-DD MM-DD]
                                                     the recovery on each pixel: a GeoTIFF of the metrics
    monitoreo ring --region JSON --out F.gpkg [--gap 150] [--width 1500] [--exclude JSON] [--within JSON]
                                                     the control ring of an affected area, matched by elevation
    monitoreo count VARIABLE --sensor S --region JSON --start D --end D [--step annual] [--csv F] [--png F]
                                                     the images and valid observations of each step, after the
                                                     pixel filters: to choose a period before analysing it
    monitoreo image VARIABLE --sensor S --region JSON --start D --end D [--out F.tif] [--rgb F.tif] [--metric median]
                    [--resolution M]                 GeoTIFF of the map of a variable aggregated in time (--out), of the
                                                     true colour of the same images (--rgb: bands red, green and blue)
                                                     or both, on the same grid
    monitoreo stats VARIABLE --sensor S --region JSON [--start D --end D] [--metric median] [--stats mean,cv,p90]
                                                     statistics of the map of a variable over each feature of the
                                                     region: mean, median, min, max, std, cv (coefficient of
                                                     variation, %) and percentiles; also the fixed layers; of a
                                                     categorical layer (ECOREGION, BIOME), the majority class (mode)
    monitoreo trend VARIABLE --sensor S --region JSON --start D --end D [--step annual|monthly|16-day]
                    [--test mk|hamed-rao|tfpw] [--csv F]
                                                     seasonal trends (Mann-Kendall and Sen) of each part of the year
    monitoreo compare VARIABLE --sensor S --region JSON --start D --end D --other-start D --other-end D [--step]
                                                     a reference period against another, by part of the year
    monitoreo areas --region JSON --landcover MAP [--year Y] [--other-year Y2] [--csv F] [--png F]
    monitoreo areas VARIABLE --sensor S --region JSON [--start D --end D] --breaks 0.2,0.4,0.6 | --trend
    monitoreo areas ECOREGION --sensor RESOLVE --region JSON
                                                     hectares and % of each class of a land cover map, of the map of a
                                                     variable cut at some values, of the trend on each pixel, or of the
                                                     classes of a categorical layer (ECOREGION, BIOME)
    monitoreo stats VARIABLE ... --zones '{"variable": "ELEVATION", "sensor": "Copernicus", "breaks": [1500, 2000]}'
                                                     the statistics of each band of another variable (elevation), or
                                                     of each class of a categorical layer: --zones '{"variable":
                                                     "BIOME", "sensor": "RESOLVE"}'
    monitoreo transect VARIABLE --sensor S --line '[[lon, lat], ...]' [--start D --end D] [--csv F] [--png F]
                                                     profile of a variable along a line, with the elevation
    monitoreo figure VARIABLE --sensor S --region JSON [--start D --end D] --out F.png|F.pdf|F.svg [--dpi 300]
                                                     figure of the map for a report or a paper: grid, scale bar,
                                                     north arrow, colour ramp and credits
    monitoreo timelapse VARIABLE --sensor S --region JSON --start D --end D --out F.gif|F.mp4
                        [--step annual|monthly|16-day|daily] [--metric median] [--fps 1]
                                                     animation of a variable: a frame per step with its date
    monitoreo series --collection ID --band B [--band-scale F] [--band-offset F] [--unit U] --region JSON ...
                                                     the same with any collection of images of Earth Engine by its ID,
                                                     instead of VARIABLE and --sensor (also image, stats, trend and
                                                     compare); image and stats also take --image ID (a fixed image,
                                                     without dates) and
                                                     --terrain slope|aspect (in degrees: its unit is then degree)
    monitoreo series --collection ID --band B1,B2 --band-reducer sum|mean ...
                                                     several bands combined on each pixel: their sum or their mean
    monitoreo datasets [TEXT] [--start D] [--end D] [--bbox W S E N] [--kind image|image_collection] [--limit N]
                                                     search the Earth Engine data catalog by words (in English), dates
                                                     and area (without Earth Engine)
    monitoreo asset ID                              what an image or collection of Earth Engine is (type, bands,
                                                     units, scale, dates, how to cite it), to give it with --collection
                                                     or --image and --band
    monitoreo community [--theme T] [--text T] [--kind image|image_collection] [--limit N] [--lang es]
                                                     the themes of the GEE Community Catalog or, with --theme, --text
                                                     or --kind, its images and collections of images (ID, type, title)
    monitoreo burn --sensor S --region JSON --start D --end D --other-start D --other-end D
                   [--index dNBR|RBR|RdNBR] [--collection ID] [--csv F] [--out F.tif]
                   [--perimeter F.gpkg [--burned-min X] [--min-ha HA]]
                                                     burn severity of a fire: hectares of the classes of the USGS
                                                     (dNBR) or of Miller & Thode 2007 (RdNBR, also with Modis), or
                                                     statistics of the RBR, before (start to end) and after
                                                     (other-start to other-end) the fire; with --perimeter, the
                                                     polygons of the burned area, to use as a region
    monitoreo download RECIPE --area FILE|JSON --out FOLDER [--dry-run]   GeoTIFFs of a recipe of variables
    monitoreo publish REPORT.yaml [...] [--site S]   publish reports in the static viewer of results (administrators)
    monitoreo publish [--remove ID] [--check] [--site S]   remove a report, or check the site; with nothing else,
                                                     update its viewer (after updating monitoreo) and its catalogue
    monitoreo publish --tags ID [TAG ...] [--site S]   the tags of a published report, without publishing it again
    monitoreo serve [SITE] [--port 8000]             the viewer of results on this computer
    monitoreo [--project P] projects                 the Google Cloud projects of your Google account (of
                                                     `earthengine authenticate`) registered in Earth Engine, for
                                                     --project (P: one more to check)
    monitoreo about [--lang es]                      what MonitorEO-OBSNEV is, who funds it and how to cite it
    monitoreo mcp [--no-update]                      server MCP (stdio) for language models, at the last version
                                                     of GitHub (installed when it starts, if needed)
    monitoreo assistant [--port 8765] [--browser] [--no-update]   AI assistant in a window of its own (or
                                                     the browser), with the language model of MonitorEO, GLM (Z.ai) or
                                                     one of Ollama and the MCP server, at the last version of GitHub

The region is a JSON dictionary, e.g. '{"wdpa_id": 555513}', '{"admin2": 141938}', '{"country": "ESP"}',
'{"island_at": [2.9, 39.6]}', '{"sea": "Alboran Sea"}' or '{"sea": 3324}' (a sea area of the IHO, by its name or its
MRGID: monitoreo seas finds them), '{"sea_at": [-2.5, 36]}' (the sea at a point), '{"biome_at": [-3.3, 37.1]}' (the
biome of RESOLVE Ecoregions 2017 at a point; by its code, 1 to 14 or 99, '{"biome_id": 12}': monitoreo classes BIOME
lists them), '{"bbox": [-3.5, 37, -3, 37.2]}' or an official perimeter, downloaded once: '{"ems": "EMSR375"}' (the
observed event of an activation of Copernicus EMS), '{"effis_id": 17545}' (a burnt area of EFFIS: monitoreo burnt
finds them), '{"wfs": URL, "layer": "BDG:ardida_2022"}' (a layer of a WFS) or '{"url": URL}' (a vector file on the
web); any region takes "within", another region, to keep only its part
inside it, e.g. the Mediterranean biome in Spain: '{"biome_id": 12, "within": {"country": "ESP"}}' (a whole biome spans
continents: give it within a region, or MODIS or the climate at an annual step). The large areas (more than 100,000
km²: a country, a biome, most seas) are computed by default on pixels of 1 to 10 km. The Earth Engine
project is --project, the variable EE_PROJECT or (download) project: of the recipe, with the Google account of
`earthengine authenticate`; without one, it computes with the shared account of MonitorEO, where each user has research
EECUs for each month, only for research. The commands that compute warn when Earth Engine has put the project in
restricted mode (it has spent its noncommercial compute quota: computations are slow and may fail with too many
requests; with the shared account, use your own project), and when
the period begins before the first image of the data or ends (or even begins) after the last one of
data that ended in the copy of the Earth Engine data catalog, which Earth Engine may have extended since (a period that
ends before the first image, falls between Landsat 5 and Landsat 8 (without --landsat7) or begins after today is an
error that says their dates); their charts say where the values come from, in a line «Data: ...» (the Earth Engine collection and its
product level). The recipe of download is a YAML
file with the variables, their metrics and the pixel sizes of the study area and of its ecoregions (see
monitoreo.recipe). The report of publish is a YAML file with its texts and the results of an analysis (see
monitoreo.publish); the site is --site, the variable MONITOREO_SITE or ~/MonitorEO/visor.
"""

import argparse
import inspect
import json
import os
import subprocess
import sys
import threading

from . import __released__, __version__


WHERE_HELP = ('only the pixels of the region whose variables pass these conditions, a JSON list, e.g. '
              '\'[{"variable": "ELEVATION", "sensor": "Copernicus", "min": 1500}]\' (each its variable aggregated '
              'over the period, between min and max), or without some land covers of a land cover map of a year, e.g. '
              '\'[{"landcover": "CORINE", "year": 2018, "exclude": ["water", "built"]}]\' (monitoreo landcover lists '
              'the maps and the land covers), or only some classes of a categorical layer (classes), or without them '
              '(exclude), e.g. \'[{"variable": "BIOME", "sensor": "RESOLVE", "classes": [12]}]\' (monitoreo classes '
              'BIOME lists them; see the wiki, Concepts)')


def _landcover(args, services):
	"""monitoreo landcover: the land cover maps and the broad land covers of the masks; with --map, the classes of that
	map in each broad land cover."""
	from . import landcover
	d = services.landcover_maps(args.lang)
	if args.map:
		try:
			key = landcover.find(args.map)['key']
		except ValueError as e:
			sys.exit(f'ERROR: {e}')
		m = next(x for x in d['maps'] if x['key'] == key)
		print(f"{m['name']} ({m['resolution_m']} m, {m['coverage']}; years {m['years']}, by default "
		      f"{m['default_year']}): {m['how']}")
		for c in d['classes']:
			print(f"  {c['key']:<10} {c['name']}: {'; '.join(m['classes'][c['key']]) or '-'}")
		return
	_table([{'key': m['key'], 'map': m['name'], 'resolution_m': m['resolution_m'], 'coverage': m['coverage'],
	         'years': m['years'], 'default_year': m['default_year']} for m in d['maps']],
	       ['key', 'map', 'resolution_m', 'coverage', 'years', 'default_year'])
	print()
	_table(d['classes'], ['key', 'name', 'help'])
	print(f"\n{d['rule']} E.g. --where '[{{\"landcover\": \"CORINE\", \"year\": 2018, \"exclude\": "
	      f"[\"water\", \"built\"]}}]'; monitoreo landcover --map CORINE lists the classes of a map.")


def _where(args):
	return json.loads(args.where) if getattr(args, 'where', None) else None


# the collections of the RdNBR of MODIS (monitoreo burn --index RdNBR --sensor Modis --collection; catalog entries 146,
# Terra, the default, and 147, Aqua)
BURN_COLLECTIONS = ('MODIS/061/MOD09GA', 'MODIS/061/MYD09GA')


PERCENTILES_HELP = ('the two percentiles of the values of the map over the region between which its colour ramp is '
                    'stretched (default: 1 99)')
SENSOR_HELP = 'the sensor of VARIABLE, e.g. Sentinel-2 (monitoreo list gives those of each variable)'
# the metrics of the images and the statistics of the region, for any variable (composite.METRICS)
METRIC_HELP = ('how the images are summarized on each pixel: mean, median, min, max, std (standard deviation), cv '
               '(coefficient of variation: 100 x std / mean, in %%), sum, count, mode or pN (percentile N, e.g. p90)')
STAT_HELP = ('how the pixels of each feature of the region are summarized: mean, median, min, max, std (standard '
             'deviation), cv (coefficient of variation, in %%) or pN (percentile N, e.g. p90)')
INTERANNUAL_HELP = ('with --temporal annual, monthly or 16-day: how the years are summarized, any metric (e.g. cv: how '
                    'much the values change from year to year, in %%)')
# the options of the data of Earth Engine given by its ID, instead of VARIABLE and --sensor (see monitoreo asset)
SOURCE_OPTIONS = {'image': '--image', 'band': '--band', 'band_reducer': '--band-reducer', 'band_scale': '--band-scale',
                  'band_offset': '--band-offset', 'unit': '--unit', 'terrain': '--terrain'}
TREND_TESTS = ('mk', 'hamed-rao', 'tfpw')  # monitoreo.trends.TESTS (without importing Earth Engine for the help)
TEST_HELP = ('the trend test: mk (Mann-Kendall, the default), hamed-rao (its variance corrected for the autocorrelation '
             'of the yearly values, Hamed & Rao 1998) or tfpw (trend-free pre-whitening, Yue et al. 2002)')


def _source_options(p, image=False):
	"""Add to the subcommand P the options of the data of Earth Engine given by its ID (IMAGE: also --image and
	--terrain, for the commands that compute a fixed layer)."""
	p.add_argument('--collection', metavar='ID',
	               help='instead of VARIABLE and --sensor: the ID of a collection of images of Earth Engine with dates, '
	                    'aggregated in time like a variable (e.g. IDAHO_EPSCOR/TERRACLIMATE; monitoreo asset ID '
	                    'describes it); with VARIABLE, one of the collections of that variable in the catalog')
	if image:
		p.add_argument('--image', metavar='ID',
		               help='instead of VARIABLE and --sensor: the ID of an image of Earth Engine, or of a collection of '
		                    'tiles (their mosaic), e.g. WORLDCLIM/V1/BIO: a fixed layer, without dates')
	p.add_argument('--band', help='the band of --collection' + (' or --image' if image else '') +
	                              ' (one, or several separated by commas with --band-reducer, e.g. aet,def; monitoreo '
	                              'asset ID lists them)')
	p.add_argument('--band-reducer', choices=('sum', 'mean'),
	               help='how several --band are combined into one value on each pixel where all of them have data: '
	                    'their sum (e.g. 12 monthly bands into the annual total) or their mean (e.g. the depth bands '
	                    'of a soil), on the pixels of the first band')
	p.add_argument('--band-scale', type=float, metavar='F',
	               help='factor of the stored values of the band (e.g. 0.1; of each band, before they are combined)')
	p.add_argument('--band-offset', type=float, metavar='F',
	               help='what is added to the values of the band after --band-scale')
	p.add_argument('--unit', help="unit of the values (after --band-scale and --band-offset) in UDUNITS, e.g. mm, degC, "
	                              "'kg m-2', 'mm day-1' or 1 (dimensionless); with several bands, that of every band "
	                              '(their sum is not turned from a rate into a total: 12 monthly bands in mm sum to '
	                              'mm)' + ('; with --terrain, none or degree' if image else ''))
	if image:
		p.add_argument('--terrain', choices=('slope', 'aspect'),
		               help='the slope or the aspect of the band of --image (e.g. of a DEM; one band), in degrees (its '
		                    'unit is then degree: give no --unit, or degree, not that of the band)')
	_topographic_option(p)


TOPOGRAPHIC_HELP = ('correct the surface reflectance of Landsat for the relief before the formula (SCS+C, Soenen et '
                    'al. 2005): for mountains, to compare slopes facing and away from the sun or dates with a low sun; '
                    'not for Sentinel-2 (already corrected), flat land, water, snow, LST, SCF, SCD, SMOD, CF, MODIS or the '
                    'climate. It costs more in Earth Engine (a regression per image)')


SNOW_NDSI_HELP = ('with the snow filter, also remove the pixels of each image whose NDSI (green, SWIR1; Hall et al. '
                  '1995) is this number or more, e.g. 0.4: the patches of snow that the QA band misses (Sentinel-2 and '
                  'Landsat; not for the NDSI, SCF, SCD and SMOD, which measure snow, and not applied to the NDWI, Chl-a, NDCI and '
                  'WAVI, as open water has a high NDSI too)')


HARMONIZE_HELP = ('turn the surface reflectance of Landsat 5 and 7 into that of Landsat 8 and 9 (Roy et al. 2016), so '
                  'that a long series has no step in 2013 (Landsat variables computed from reflectances; not LST, SCF, '
                  'SCD, SMOD or CF)')
LANDSAT7_HELP = ('use Landsat 7 also after 2003-05-31, with the stripes without data of the failure of its scan line '
                 'corrector: more images from 2003 to 2024, and images between Landsat 5 and Landsat 8 (2012-05-05 to '
                 '2013-03-18)')
MIN_COVERAGE_HELP = ('leave without value the steps whose valid pixels (after the pixel filters) are less than this '
                     'fraction of the pixels of the region, e.g. 0.5; the CSV gets their coverage')


def _ring_options(p, name='--ring'):
	"""The options of the control ring (monitoreo.control) of the parser P."""
	p.add_argument(name, action='store_true',
	               help='the region is the affected area: also the series of a control ring around it (its pixels '
	                    'matched by elevation, percentiles 5 to 95 of the affected area) and of their difference')
	p.add_argument('--ring-gap', type=float, metavar='M', help='metres between the affected area and the ring (150)')
	p.add_argument('--ring-width', type=float, metavar='M', help='width of the ring in metres (1500)')
	p.add_argument('--ring-exclude', metavar='JSON', help='a region left out of the ring: other fires or disturbances')
	p.add_argument('--ring-within', metavar='JSON', help='a region the ring stays inside, e.g. the protected area')
	p.add_argument('--ring-match', nargs='*', metavar='VARIABLE',
	               help='fixed layers that match the pixels, ELEVATION (the default) and SLOPE; none: no matching')


def _ring(args):
	"""The option ring of the services from the options of _ring_options: None without --ring."""
	if not getattr(args, 'ring', False):
		given = [o for o in ('ring_gap', 'ring_width', 'ring_exclude', 'ring_within', 'ring_match')
		         if getattr(args, o, None) is not None]
		if given:
			sys.exit(f"ERROR: {', '.join('--' + g.replace('_', '-') for g in given)}: only with --ring")
		return None
	out = {'gap': args.ring_gap, 'width': args.ring_width,
	       'exclude': json.loads(args.ring_exclude) if args.ring_exclude else None,
	       'within': json.loads(args.ring_within) if args.ring_within else None,
	       'match': args.ring_match}
	return {k: v for k, v in out.items() if v is not None} or True


def _topographic_option(p):
	p.add_argument('--topographic-correction', action='store_true', help=TOPOGRAPHIC_HELP)
	p.add_argument('--snow-ndsi', type=float, metavar='NDSI', help=SNOW_NDSI_HELP)
	p.add_argument('--harmonize', action='store_true', help=HARMONIZE_HELP)
	p.add_argument('--landsat7', action='store_true', help=LANDSAT7_HELP)


# the themes of the data of Earth Engine outside the catalog (catalog.OTHER_THEMES), with the commands and options of
# the command line
OTHER_THEMES = {
	'earth_engine': 'any image or collection of images of Earth Engine by its ID: monitoreo asset ID describes it (its '
	                'bands, units and dates); then compute it with --collection (or --image, in monitoreo image) and '
	                '--band (several with --band-reducer)',
	'community': 'the datasets of the GEE Community Catalog by its own themes: monitoreo community lists its themes '
	             'and, with --theme or --text, their datasets; monitoreo asset ID describes one; then compute it with '
	             '--collection (or --image, in monitoreo image) and --band (several with --band-reducer)'}


def _other_theme(theme):
	"""The theme of catalog.OTHER_THEMES named THEME (its key, or its name in English or Spanish, as services read
	them), or None."""
	from . import catalog
	low = str(theme or '').strip().lower()
	return next((t for t in catalog.OTHER_THEMES if low and low in (t['key'], t['en'].lower(), t['es'].lower())), None)


def _error(e, args):
	"""The message of the error E of the services for a command that computes ARGS.source: when the data given with
	--collection have to be given as an image (the services say «give it as an image»: an image, or a collection of
	tiles without dates), with the option of the command line that does it."""
	text = f'ERROR: {e}'
	asset = None if 'variable' in args.source else args.source.get('collection')
	if asset and 'give it as an image' in str(e):
		reducer = args.source.get('band_reducer')
		text += (f'; in the command line, --image {asset} instead of --collection' if hasattr(args, 'image') else
		         f"; in the command line, monitoreo image --image {asset} --band {args.source.get('band')}"
		         f"{f' --band-reducer {reducer}' if reducer else ''} (a GeoTIFF)")
	return text


def _source(args, parser):
	"""The data that a command computes, as the keywords of services: VARIABLE and --sensor (a variable of the catalog;
	--collection, one of its collections), or --collection or --image and --band (any data of Earth Engine by its ID;
	several bands, separated by commas, with --band-reducer), with --band-scale, --band-offset, --unit and, for an image
	of one band, --terrain. Else the error of PARSER, before Earth Engine (those of the bands in the words of the
	services: variable.check_bands)."""
	given = {k: getattr(args, k, None) for k in SOURCE_OPTIONS}
	given = {k: v for k, v in given.items() if v is not None and v != ''}
	image = 'image' in given
	ids = '--collection or --image' if hasattr(args, 'image') else '--collection'  # --image: the commands image, stats
	if args.variable:
		if '/' in args.variable:  # an ID of Earth Engine given as a variable of the catalog (none has '/'), sensor or not
			parser.error(f'{args.variable} is not a variable of the catalog (monitoreo list): give an ID of Earth Engine '
			             f'with {ids} and --band, instead of VARIABLE (monitoreo asset ID says which)')
		if not args.sensor:
			parser.error(f'give the sensor of {args.variable} (--sensor; monitoreo list gives those of each variable)')
		if given:
			parser.error(f"{', '.join(SOURCE_OPTIONS[k] for k in given)}: only for the data of Earth Engine given by "
			             f'its ID ({ids} instead of VARIABLE and --sensor)')
		return dict({k: v for k, v in (('variable', args.variable), ('sensor', args.sensor),
		                               ('collection', args.collection)) if v}, **_topographic(args))
	if args.sensor:
		parser.error('--sensor is for the variables of the catalog (with VARIABLE): the data of Earth Engine given by its '
		             f'ID take {ids}, and --band')
	asset = args.collection or given.get('image')
	if not asset:
		parser.error(f'give VARIABLE and --sensor (a variable of the catalog: monitoreo list), or {ids} and --band (any '
		             'data of Earth Engine by its ID: monitoreo asset ID)')
	if args.collection and image:
		parser.error('give --collection (images with dates) or --image (a fixed image), not both')
	if 'band' not in given:
		parser.error(f'give --band: the band of {asset} (one, or several separated by commas with --band-reducer; '
		             f'monitoreo asset {asset} lists them)')
	from . import variable
	try:  # several bands without --band-reducer, --band-reducer with one band, a band twice, --terrain with several
		variable.check_bands(dict(given), asset)
	except ValueError as e:
		parser.error(str(e))
	if 'terrain' in given and not image:
		parser.error('--terrain is for --image (a fixed layer, e.g. a DEM), not for --collection')
	if getattr(args, 'topographic_correction', False):
		parser.error('--topographic-correction is for the surface reflectance of Landsat of the catalog (VARIABLE and '
		             '--sensor Landsat), not for the data of Earth Engine given by its ID')
	if getattr(args, 'snow_ndsi', None) is not None:
		parser.error('--snow-ndsi is for the variables of Sentinel-2 and Landsat of the catalog, not for the data of '
		             'Earth Engine given by its ID')
	for o in ('harmonize', 'landsat7'):
		if getattr(args, o, False):
			parser.error(f'--{o} is for the variables of Landsat of the catalog, not for the data of Earth Engine given '
			             'by its ID')
	return dict(given, **({'collection': args.collection} if args.collection else {}))


def _topographic(args):
	"""The quality of the topographic correction, of the snow by its NDSI and of Landsat 5 and 7, if asked
	(--topographic-correction, --snow-ndsi, --harmonize, --landsat7)."""
	q = {}
	if getattr(args, 'topographic_correction', False):
		q['topographic'] = True
	if getattr(args, 'snow_ndsi', None) is not None:
		q['snow_ndsi'] = args.snow_ndsi
	for o in ('harmonize', 'landsat7'):
		if getattr(args, o, False):
			q[o] = True
	return {'quality': q} if q else {}


def _table(rows, cols):
	widths = {c: max(len(c), *(len(str(r.get(c, ''))) for r in rows)) if rows else len(c) for c in cols}
	print('  '.join(c.ljust(widths[c]) for c in cols))
	for r in rows:
		print('  '.join(str(r.get(c, '')).ljust(widths[c]) for c in cols))


# the options of several numbers, which also take them with commas (see _list_args)
LIST_OPTIONS = ('--bbox', '--ylim', '--other-ylim')


def _list_args(argv):
	"""ARGV with --bbox=W,S,E,N and --bbox W,S,E,N as --bbox W S E N, and so the other LIST_OPTIONS (--ylim=-1,1 as
	--ylim -1 1): argparse reads -3.6,36.9,... (a west below 0) as an option, but -3.6 alone as a number."""
	out = []
	for a in argv:
		name, equals, value = a.partition('=')
		if equals and name in LIST_OPTIONS:
			out += [name] + [x for x in value.split(',') if x.strip()]
		elif out and out[-1] in LIST_OPTIONS and ',' in a:
			out += [x for x in a.split(',') if x.strip()]
		else:
			out.append(a)
	return out


def main(argv=None):
	from . import about
	parser = argparse.ArgumentParser(prog='monitoreo', description=about.DESCRIPTION['en'],
	                                 epilog=f"{about.ACKNOWLEDGEMENTS['en']} How to cite: {about.CITATION}")
	parser.add_argument('--version', action='version', version=f'{__version__} (released {__released__})')
	parser.add_argument('--project', help='Earth Engine project, with your account of `earthengine authenticate` '
	                    '(default: EE_PROJECT; none: the shared account of MonitorEO)')
	sub = parser.add_subparsers(dest='cmd', required=True)
	p = sub.add_parser('list', help='variables of the catalog')
	p.add_argument('--sensor')
	p.add_argument('--theme', help='only those of a theme: vegetation, water, snow, fire, energy, atmosphere, climate, '
	                               'terrain or ecosystems (other data of Earth Engine: monitoreo asset and monitoreo '
	                               'community)')
	p.add_argument('--text')
	p.add_argument('--lang', default='en', choices=('en', 'es'))
	info = p = sub.add_parser('info', help='everything about a variable')
	p.add_argument('variable')
	p.add_argument('--sensor')
	p = sub.add_parser('classes', help='the classes of a categorical layer (ECOREGION, BIOME of sensor RESOLVE): their '
	                                   'code (for --where with classes or exclude, and for --zones), name, colour and '
	                                   'biome (without Earth Engine)')
	p.add_argument('variable', help='a categorical layer: ECOREGION or BIOME')
	p.add_argument('--sensor', default='RESOLVE', help='its sensor (default: RESOLVE)')
	p.add_argument('--text', help='only those with these words at the start of a word of their code, name or biome, '
	                              'e.g. Iberian')
	p.add_argument('--limit', type=int, help='at most this number of classes (default: all)')
	p.add_argument('--lang', default='en', choices=('en', 'es'), help='language of the names of the biomes')
	p = sub.add_parser('parks', help='protected areas of WDPA by name')
	p.add_argument('text')
	p.add_argument('--limit', type=int, default=20)
	p.add_argument('--ramsar', action='store_true', help='only the Ramsar sites')
	p = sub.add_parser('units', help='administrative units of FAO GAUL 2025 by name, or the municipalities of Spain')
	p.add_argument('text')
	p.add_argument('--level', type=int, default=1, choices=(1, 2, 3),
	               help='1: regions, states...; 2: provinces, districts...; 3: the municipalities of Spain (of the '
	                    'IGN, without Earth Engine: --region \'{"admin3": "18134"}\')')
	p.add_argument('--country', help='ISO3 code, e.g. ESP')
	p.add_argument('--limit', type=int, default=20)
	p = sub.add_parser('seas', help='oceans and seas (the sea areas of the IHO, Marine Regions) by name, without Earth '
	                                'Engine: --region \'{"sea": 3324}\' or \'{"sea": "Alboran Sea"}\'')
	p.add_argument('text')
	p.add_argument('--limit', type=int, default=20)
	p = sub.add_parser('burnt', help='burnt areas of EFFIS (2000 to today) in a region or a country, the largest first: '
	                                 'their official perimeter is --region \'{"effis_id": ID}\'')
	p.add_argument('--region', help='JSON dictionary: the burnt areas that touch it (its bounding box is asked to EFFIS)')
	p.add_argument('--country', help='two-letter code, e.g. ES or PT (without --region)')
	p.add_argument('--start', help='that began from this day (YYYY-MM-DD)')
	p.add_argument('--end', help='that began until this day (YYYY-MM-DD)')
	p.add_argument('--min-area', type=float, help='hectares')
	p.add_argument('--limit', type=int, default=20)
	p = sub.add_parser('asset', help='what an image or collection of images of Earth Engine is: type, bands, units, '
	                                 'scale, dates and how to cite it (reads its metadata in Earth Engine)')
	p.add_argument('asset', metavar='ID', help="its ID, as in ee.ImageCollection('ID') (e.g. IDAHO_EPSCOR/TERRACLIMATE)")
	p = sub.add_parser('datasets', help='search the Earth Engine data catalog by words (in English), dates and area '
	                                    '(without Earth Engine)')
	p.add_argument('text', nargs='*', help='words of its title, ID, keywords or description, e.g. snow cover')
	p.add_argument('--start', help='collections of images with data from this day (YYYY-MM-DD); the images, fixed '
	                               'layers without dates, whatever their dates')
	p.add_argument('--end', help='collections of images with data until this day')
	p.add_argument('--bbox', nargs=4, type=float, metavar=('W', 'S', 'E', 'N'),
	               help='with data over this area: west, south, east and north in degrees, e.g. --bbox -3.6 36.9 -2.6 37.3 '
	                    '(or --bbox=-3.6,36.9,-2.6,37.3)')
	p.add_argument('--kind', choices=('image', 'image_collection'), help='only images or only collections of images')
	p.add_argument('--limit', type=int, default=20, help='at most this number of datasets (default 20, at most 100)')
	p = sub.add_parser('community', help='the themes of the GEE Community Catalog, or its images and collections of '
	                                     'images (without Earth Engine)')
	p.add_argument('--theme', help='only those of a theme of the catalog (its name in English or Spanish, or part of it)')
	p.add_argument('--text', help='only those with these words in their title, ID, provider or tags')
	p.add_argument('--kind', choices=('image', 'image_collection'), help='only images or only collections of images')
	p.add_argument('--limit', type=int, help='at most this number of datasets (default: all)')
	p.add_argument('--lang', default='en', choices=('en', 'es'), help='language of the names of the themes')
	p = sub.add_parser('landcover', help='the land cover maps of the land cover masks (--where with landcover, year and '
	                                     'exclude), their years and the classes of each map in each broad land cover '
	                                     '(without Earth Engine)')
	p.add_argument('--map', help='only this map: its classes in each broad land cover')
	p.add_argument('--lang', default='en', choices=('en', 'es'), help='language of the names of the land covers')
	computes = {}  # the subcommands of a variable or of data of Earth Engine by its ID, for the errors of _source
	computes['series'] = p = sub.add_parser('series', help='time series of a variable over a region')
	p.add_argument('variable', nargs='?', help='a variable of the catalog (monitoreo list), with --sensor')
	p.add_argument('--sensor', help=SENSOR_HELP)
	_source_options(p)
	p.add_argument('--region', required=True, help='JSON dictionary, e.g. \'{"wdpa_id": 555513}\' or, with within, '
	                                                '\'{"biome_id": 12, "within": {"country": "ESP"}}\'')
	p.add_argument('--where', help=WHERE_HELP)
	p.add_argument('--start', required=True)
	p.add_argument('--end', required=True)
	p.add_argument('--step', default='monthly', choices=('daily', '16-day', 'monthly', 'annual'))
	p.add_argument('--metric', default='mean', help=METRIC_HELP + ' (default: mean)')
	p.add_argument('--stat', default='mean', help=STAT_HELP + ' (default: mean)')
	p.add_argument('--scale', type=float)
	p.add_argument('--csv')
	p.add_argument('--png')
	p.add_argument('--doy', action='store_true', help='the chart with a line per year over the days of the year, to '
	                                                  'compare the years (not with --step annual)')
	p.add_argument('--interannual', metavar='METRIC',
	               help='with --doy, the seasonal profile instead: a line per variable, this metric of the values of each '
	                    'step of the year (each month, 16-day period or day) in the years of the period: mean, median, '
	                    'min, max, std (sample standard deviation), cv (coefficient of variation, in %%) or pN '
	                    '(percentile N, e.g. p25) (default with --other-variable: median)')
	p.add_argument('--other-variable', metavar='VARIABLE',
	               help='with --doy: a second variable of the catalog on a right y axis of the profile (e.g. NDVI, with '
	                    'NDSI as VARIABLE), computed as VARIABLE: the same region, period, step, metrics and pixel '
	                    'filters')
	p.add_argument('--other-sensor', help='the sensor of --other-variable (default: --sensor)')
	p.add_argument('--ylim', nargs=2, type=float, metavar=('MIN', 'MAX'),
	               help='with --doy: the range of the (left) y axis, e.g. --ylim -1 1 (default: from the minimum to the '
	                    'maximum of the values of its variable)')
	p.add_argument('--other-ylim', nargs=2, type=float, metavar=('MIN', 'MAX'),
	               help='the range of the right y axis, that of --other-variable (default as --ylim)')
	p.add_argument('--min-coverage', type=float, metavar='FRACTION', help=MIN_COVERAGE_HELP)
	_ring_options(p)
	p = sub.add_parser('recovery-map', help='the recovery after a disturbance on each pixel: a GeoTIFF of the metrics of '
	                                         'Marcos et al. (2023) of the annual series of each pixel')
	p.add_argument('variable', nargs='?', help='a variable of the catalog (monitoreo list), with --sensor')
	p.add_argument('--sensor', help=SENSOR_HELP)
	p.add_argument('--region', required=True, help='JSON dictionary of the area, e.g. \'{"file": "fire.gpkg"}\'')
	p.add_argument('--where', help=WHERE_HELP)
	p.add_argument('--start', required=True, help='first day: at least --reference-years before the event')
	p.add_argument('--end', required=True)
	p.add_argument('--event', required=True, help='date of the disturbance, YYYY-MM-DD')
	p.add_argument('--season', nargs=2, metavar=('MM-DD', 'MM-DD'), help='only these days of each year, e.g. 07-01 09-30')
	p.add_argument('--metric', default='median', help=METRIC_HELP + ' (default: median)')
	p.add_argument('--reference-years', type=int, default=3, help='years before the event of the reference (default 3)')
	p.add_argument('--equilibrium', type=float, default=0.05, help='relative change of a stable year (default 0.05)')
	p.add_argument('--resolution', type=float, help='pixel size in metres (default: that of the data)')
	p.add_argument('--out', help='GeoTIFF of the metrics (the yearly values go to <out>_yearly.tif)')
	p = sub.add_parser('ring', help='the control ring of an affected area: a vector file of the '
	                                                   'affected area and the ring, and the where that matches them')
	p.add_argument('--region', required=True, help='JSON dictionary of the affected area, e.g. \'{"file": "fire.gpkg"}\'')
	p.add_argument('--out', required=True, help='vector file to write (.gpkg, .geojson or .shp)')
	p.add_argument('--gap', type=float, default=150, help='metres between the affected area and the ring (150)')
	p.add_argument('--width', type=float, default=1500, help='width of the ring in metres (1500)')
	p.add_argument('--exclude', metavar='JSON', help='a region left out of the ring: other fires or disturbances')
	p.add_argument('--within', metavar='JSON', help='a region the ring stays inside, e.g. the protected area')
	p.add_argument('--match', nargs='*', metavar='VARIABLE', help='fixed layers that match the pixels (ELEVATION, SLOPE)')
	computes['recovery'] = p = sub.add_parser('recovery', help='severity and recovery after a disturbance (Marcos et al. '
	                                                           '2023): S95, DIT, RRT, RET of the affected area, its control '
	                                                           'and their difference')
	p.add_argument('variable', nargs='?', help='a variable of the catalog (monitoreo list), with --sensor')
	p.add_argument('--sensor', help=SENSOR_HELP)
	_source_options(p)
	p.add_argument('--region', required=True, help='JSON dictionary with the affected area and the control as two '
	                                                'features, e.g. \'{"file": "zones.gpkg", "name_field": "region"}\'')
	p.add_argument('--where', help=WHERE_HELP)
	p.add_argument('--start', required=True, help='first day: at least --reference-years before the event')
	p.add_argument('--end', required=True)
	p.add_argument('--event', required=True, help='date of the disturbance, YYYY-MM-DD')
	p.add_argument('--affected', help='name of the affected feature of the region (default: the only one)')
	p.add_argument('--control', help='name of the control feature: also its metrics and those of the difference')
	_ring_options(p)
	p.add_argument('--step', default='monthly', choices=('monthly', '16-day', 'annual'))
	p.add_argument('--metric', default='mean', help=METRIC_HELP + ' (default: mean)')
	p.add_argument('--stat', default='mean', help=STAT_HELP + ' (default: mean)')
	p.add_argument('--reference-years', type=int, default=3, help='years before the event of the reference (default 3)')
	p.add_argument('--equilibrium', type=float, default=0.05,
	               help='relative change of the yearly medians below which the series is stable, RET (default 0.05)')
	p.add_argument('--min-coverage', type=float, metavar='FRACTION', help=MIN_COVERAGE_HELP)
	p.add_argument('--scale', type=float)
	p.add_argument('--csv')
	p.add_argument('--png')
	computes['count'] = p = sub.add_parser('count', help='images and valid observations of a variable per step over a '
	                                                     'region, after the pixel filters: to choose a period before '
	                                                     'analysing it')
	p.add_argument('variable', nargs='?', help='a variable of the catalog (monitoreo list), with --sensor')
	p.add_argument('--sensor', help=SENSOR_HELP)
	_source_options(p)
	p.add_argument('--region', required=True, help='JSON dictionary, e.g. \'{"wdpa_id": 555513}\'')
	p.add_argument('--where', help=WHERE_HELP)
	p.add_argument('--start', required=True)
	p.add_argument('--end', required=True)
	p.add_argument('--step', default='annual', choices=('daily', '16-day', 'monthly', 'annual'),
	               help='a row per year (default), month, 16 days or day with images')
	p.add_argument('--scale', type=float)
	p.add_argument('--csv')
	p.add_argument('--png')
	computes['image'] = image = p = sub.add_parser('image', help='GeoTIFF of the map of a variable over a region, '
	                                                             'aggregated in time, and of the true colour of the '
	                                                             'same images')
	p.add_argument('variable', nargs='?', help='a variable of the catalog (monitoreo list), with --sensor')
	p.add_argument('--sensor', help=SENSOR_HELP)
	_source_options(p, image=True)
	p.add_argument('--region', required=True, help='JSON dictionary, e.g. \'{"bbox": [-3.5, 37, -3, 37.2]}\'')
	p.add_argument('--where', help=WHERE_HELP)
	p.add_argument('--start', help='first day (not for the fixed layers: ELEVATION and SLOPE of sensor Copernicus, '
	                               'TWI of sensor "MERIT Hydro", the BIO variables of WorldClim; nor for --image)')
	p.add_argument('--end', help='last day (not for the fixed layers)')
	p.add_argument('--metric', default='median', help=METRIC_HELP + ' (default: median)')
	p.add_argument('--temporal', default='period', choices=('period', 'annual', 'monthly', '16-day'))
	p.add_argument('--interannual', default='mean', help=INTERANNUAL_HELP)
	p.add_argument('--resolution', type=float, help='pixel size in metres (default: that of the data; 1 to 10 km over '
	                                                'more than 100,000 km²)')
	p.add_argument('--out', help='GeoTIFF file of the variable')
	p.add_argument('--vmin', type=float, help='value of the first colour of its preview, README and QGIS style '
	                                         '(default: the low percentile of the values of the file); with --rgb and '
	                                         'without --out, the reflectance of the true colour')
	p.add_argument('--vmax', type=float, help='value of the last colour (default: the high percentile)')
	p.add_argument('--percentiles', nargs=2, type=float, metavar=('LOW', 'HIGH'),
	               help=PERCENTILES_HELP + '; with --rgb and without --out, those of the true colour (default 2 98)')
	p.add_argument('--rgb', metavar='FILE', help='GeoTIFF file of the true colour of the same images and pixels: bands '
	                                             'red, green and blue (surface reflectance), with the same metric; '
	                                             'with --out too, on its grid. Only the variables of Sentinel-2 and '
	                                             'Landsat and the cloud frequency of MODIS (rgb in monitoreo info), '
	                                             'with metric median, mean, min, max or pN')
	from .catalog import REGION_STATS, REGION_STATS_ZONES
	computes['stats'] = p = sub.add_parser('stats', help='statistics of the map of a variable over each feature of a '
	                                                     'region (also the fixed layers)')
	p.add_argument('variable', nargs='?', help='a variable of the catalog (monitoreo list), with --sensor')
	p.add_argument('--sensor', help=SENSOR_HELP)
	_source_options(p, image=True)
	p.add_argument('--region', required=True, help='JSON dictionary, e.g. \'{"wdpa_id": 555513}\' or the biome at '
	                                                'a point, \'{"biome_at": [-3.3, 37.1]}\'')
	p.add_argument('--where', help=WHERE_HELP)
	p.add_argument('--start', help='first day (not for the fixed layers: ELEVATION and SLOPE of sensor Copernicus, '
	                               'TWI of sensor "MERIT Hydro", the BIO variables of WorldClim; nor for --image)')
	p.add_argument('--end', help='last day (not for the fixed layers)')
	p.add_argument('--metric', default='median', help=METRIC_HELP + ' (default: median)')
	p.add_argument('--temporal', default='period', choices=('period', 'annual', 'monthly', '16-day'))
	p.add_argument('--interannual', default='mean', help=INTERANNUAL_HELP)
	p.add_argument('--stats', help='the statistics over each feature, separated by commas: mean, median, min, max, std '
	                               '(standard deviation), cv (coefficient of variation, in %%) and pN (percentile N) '
	                               f"(default: {','.join(REGION_STATS)}; with --zones, {','.join(REGION_STATS_ZONES)}); "
	                               'of a categorical layer (ECOREGION, BIOME), mode (the majority class, the default) '
	                               'and count')
	p.add_argument('--scale', type=float, help='pixel size of the statistics in metres (default: that of the data, or '
	                                           'bigger over big regions: 1 to 10 km over more than 100,000 km²)')
	p.add_argument('--zones', help='the statistics of each band of another variable instead, a JSON dictionary, e.g. '
	                               '\'{"variable": "ELEVATION", "sensor": "Copernicus", "breaks": [1500, 2000, 2500]}\', '
	                               'or of each class of a categorical layer, without breaks, e.g. \'{"variable": "BIOME", '
	                               '"sensor": "RESOLVE"}\' (optionally "classes": the codes of those to keep)')
	p.add_argument('--csv', help='CSV file of the statistics')
	p.add_argument('--png', help='with --zones, chart of the statistics of each zone (PNG)')
	computes['transect'] = p = sub.add_parser('transect', help='profile of the map of a variable along a line, with the '
	                                                           'elevation')
	p.add_argument('variable', nargs='?', help='a variable of the catalog (monitoreo list), with --sensor')
	p.add_argument('--sensor', help=SENSOR_HELP)
	_source_options(p, image=True)
	p.add_argument('--line', required=True, help='the line, a JSON list of points [[lon, lat], ...] or a GeoJSON '
	                                             'LineString')
	p.add_argument('--where', help=WHERE_HELP)
	p.add_argument('--start', help='first day (not for the fixed layers)')
	p.add_argument('--end', help='last day')
	p.add_argument('--metric', default='median', help=METRIC_HELP + ' (default: median)')
	p.add_argument('--temporal', default='period', choices=('period', 'annual', 'monthly', '16-day'))
	p.add_argument('--interannual', default='mean', help=INTERANNUAL_HELP)
	p.add_argument('--spacing', type=float, help='length of the segments in metres (default: the line / --points, at '
	                                             'least a pixel of the data)')
	p.add_argument('--points', type=int, default=100, help='segments of the line (default 100)')
	p.add_argument('--csv')
	p.add_argument('--png')
	for name, help_ in (('trend', 'seasonal trends (Mann-Kendall and Sen) of a variable over a region'),
	                    ('compare', 'a reference period against another, by part of the year')):
		computes[name] = p = sub.add_parser(name, help=help_)
		p.add_argument('variable', nargs='?', help='a variable of the catalog (monitoreo list), with --sensor')
		p.add_argument('--sensor', help=SENSOR_HELP)
		_source_options(p)
		p.add_argument('--region', required=True, help='JSON dictionary, e.g. \'{"wdpa_id": 555513}\'')
		p.add_argument('--where', help=WHERE_HELP)
		p.add_argument('--start', required=True, help='first day (of the reference period, for compare)')
		p.add_argument('--end', required=True)
		if name == 'compare':
			p.add_argument('--other-start', required=True, help='first day of the other period')
			p.add_argument('--other-end', required=True)
		p.add_argument('--step', default='annual' if name == 'trend' else 'monthly', choices=('monthly', '16-day', 'annual'))
		p.add_argument('--metric', default='mean', help=METRIC_HELP + ' (default: mean)')
		p.add_argument('--stat', default='mean', help=STAT_HELP + ' (default: mean)')
		if name == 'trend':
			p.add_argument('--test', default='mk', choices=TREND_TESTS, help=TEST_HELP)
		p.add_argument('--min-coverage', type=float, metavar='FRACTION', help=MIN_COVERAGE_HELP)
		p.add_argument('--scale', type=float)
		p.add_argument('--csv')
		p.add_argument('--png')
	areas = computes['areas'] = p = sub.add_parser('areas', help='hectares and %% of each class of a land cover map, of '
	                                                             'the map of a variable cut at some values, of the '
	                                                             'trend of a variable on each pixel, or of the classes '
	                                                             'of a categorical layer')
	p.add_argument('variable', nargs='?', help='a variable of the catalog (monitoreo list), with --sensor; none with '
	                                           '--landcover; a categorical layer (ECOREGION, BIOME of sensor RESOLVE) '
	                                           'without --breaks nor --trend: its own classes')
	p.add_argument('--sensor', help=SENSOR_HELP)
	_source_options(p, image=True)
	p.add_argument('--region', required=True, help='JSON dictionary, e.g. \'{"wdpa_id": 555513}\'')
	p.add_argument('--where', help=WHERE_HELP)
	p.add_argument('--landcover', metavar='MAP', help='a land cover map (monitoreo landcover lists them): its classes, '
	                                                  'with their broad land cover')
	p.add_argument('--year', type=int, help='with --landcover, the year of the map (default: its last one)')
	p.add_argument('--other-year', type=int, metavar='YEAR',
	               help='with --landcover, the changes of the map from --year to this year: the hectares of each pair '
	                    'of classes and, with --png, a Sankey diagram of the broad land covers')
	p.add_argument('--breaks', help='the values where to cut the map of the variable, separated by commas, e.g. '
	                                '1500,2000,2500 for ELEVATION (below 1500, 1500 to 2000, ...)')
	p.add_argument('--trend', action='store_true', help='the classes of the trend of the variable on each pixel: '
	                                                    'significant decrease, no significant trend and increase')
	p.add_argument('--start', help='first day (not for the fixed layers nor --landcover)')
	p.add_argument('--end', help='last day')
	p.add_argument('--metric', help=METRIC_HELP + ' (default: median; with --trend, that of each year: mean)')
	p.add_argument('--temporal', default='period', choices=('period', 'annual', 'monthly', '16-day'))
	p.add_argument('--interannual', default='mean', help=INTERANNUAL_HELP)
	p.add_argument('--step', default='annual', choices=('monthly', '16-day', 'annual'), help='with --trend')
	p.add_argument('--part', type=int, help='with --trend and --step monthly or 16-day: the month (1-12) or 16 days')
	p.add_argument('--alpha', type=float, default=0.05, help='with --trend: significant if p < alpha (default 0.05)')
	p.add_argument('--test', default='mk', choices=TREND_TESTS, help='with --trend: ' + TEST_HELP)
	p.add_argument('--scale', type=float, help='pixel size in metres (default: that of the data, bigger in big regions: '
	                                           '1 to 10 km over more than 100,000 km²)')
	p.add_argument('--csv')
	p.add_argument('--png')
	computes['figure'] = p = sub.add_parser('figure', help='figure of the map of a variable for a report or a paper: '
	                                                       'grid, scale bar, north arrow, colour ramp and credits')
	p.add_argument('variable', nargs='?', help='a variable of the catalog (monitoreo list), with --sensor')
	p.add_argument('--sensor', help=SENSOR_HELP)
	_source_options(p, image=True)
	p.add_argument('--region', required=True, help='JSON dictionary, e.g. \'{"wdpa_id": 389011}\'')
	p.add_argument('--where', help=WHERE_HELP)
	p.add_argument('--start', help='first day (not for the fixed layers)')
	p.add_argument('--end', help='last day')
	p.add_argument('--metric', default='median', help=METRIC_HELP + ' (default: median)')
	p.add_argument('--temporal', default='period', choices=('period', 'annual', 'monthly', '16-day'))
	p.add_argument('--interannual', default='mean', help=INTERANNUAL_HELP)
	p.add_argument('--vmin', type=float, help='value of the first colour (default: the low percentile of the map)')
	p.add_argument('--vmax', type=float, help='value of the last colour (default: the high percentile of the map)')
	p.add_argument('--percentiles', nargs=2, type=float, metavar=('LOW', 'HIGH'),
	               help=PERCENTILES_HELP)
	p.add_argument('--title', help='title of the figure (default: that of the map)')
	p.add_argument('--dpi', type=int, default=300, help='resolution of a PNG (default: 300)')
	p.add_argument('--out', required=True, help='the figure: PNG (.png), PDF (.pdf) or SVG (.svg)')
	computes['timelapse'] = p = sub.add_parser('timelapse', help='animation of a variable over a region (a timelapse): '
	                                                             'a frame per step of the period, with its date')
	p.add_argument('variable', nargs='?', help='a variable of the catalog (monitoreo list), with --sensor')
	p.add_argument('--sensor', help=SENSOR_HELP)
	_source_options(p)
	p.add_argument('--region', required=True, help='JSON dictionary, e.g. \'{"bbox": [-3.5, 37, -3, 37.2]}\'')
	p.add_argument('--where', help=WHERE_HELP)
	p.add_argument('--start', required=True)
	p.add_argument('--end', required=True)
	p.add_argument('--step', default='annual', choices=('annual', 'monthly', '16-day', 'daily'),
	               help='a frame per year (default), month, 16 days or day with images (at most 120 frames)')
	p.add_argument('--metric', default='median', help=METRIC_HELP + ' (default: median)')
	p.add_argument('--vmin', type=float, help='value of the first colour of every frame (default: the low percentile '
	                                         'of the values of each frame)')
	p.add_argument('--vmax', type=float, help='value of the last colour of every frame (default: the high percentile)')
	p.add_argument('--percentiles', nargs=2, type=float, metavar=('LOW', 'HIGH'),
	               help=PERCENTILES_HELP)
	p.add_argument('--own-colours', action='store_false', dest='same_colours',
	               help='each frame with its own colour ramp (the percentiles of its own values), instead of one ramp '
	                    'for every frame, from the percentiles of the map of the whole period (with --metric sum or '
	                    'count, of the median of the frames), the default')
	p.add_argument('--same-colours', action='store_true', help=argparse.SUPPRESS)  # the default: kept for scripts
	p.add_argument('--fps', type=float, default=1, help='frames per second (default: 1)')
	p.add_argument('--dimensions', type=int, default=600, help='width or height of the map in pixels (default: 600)')
	p.add_argument('--out', required=True, help='GIF (.gif) or video (.mp4, needs ffmpeg) of the animation')
	burn = p = sub.add_parser('burn', help='burn severity of a fire: dNBR with the classes of the USGS, the RBR, or the '
	                                       'RdNBR with the classes of Miller & Thode 2007')
	p.add_argument('--sensor', default='Sentinel-2', choices=('Sentinel-2', 'Landsat', 'Modis'),
	               help='Sentinel-2 (20 m, since 2017), Landsat (30 m, since 1984) or Modis '
	                    '(500 m, since 2000; only with --index RdNBR, whose classes are then approximate: a pixel of '
	                    '500 m mixes burned and unburned land)')
	p.add_argument('--region', required=True, help='JSON dictionary, e.g. \'{"bbox": [-5.23, 36.47, -5.10, 36.57]}\'')
	p.add_argument('--where', help=WHERE_HELP.replace('over the period,', 'over the period before the fire,'))
	p.add_argument('--start', required=True, help='first day of the period before the fire')
	p.add_argument('--end', required=True, help='last day of the period before the fire')
	p.add_argument('--other-start', required=True, help='first day of the period after the fire')
	p.add_argument('--other-end', required=True, help='last day of the period after the fire')
	p.add_argument('--index', default='dNBR', choices=('dNBR', 'RBR', 'RdNBR'),
	               help='dNBR, with the classes of the USGS (default); RBR, the Relativized Burn Ratio (continuous, '
	                    'without classes); or RdNBR, the relative dNBR of Miller & Thode 2007 (Remote Sensing of '
	                    'Environment, https://doi.org/10.1016/j.rse.2006.12.006), dNBR / sqrt(|NBR before|) with |NBR '
	                    'before| at least 0.001 (Howe et al. 2022), for heterogeneous vegetation and to compare fires, '
	                    'with the classes of the article (unchanged, low, moderate and high severity; unchanged is not '
	                    'unburned), on the scale of the dNBR, without the factor 1000 of the article (0.641 here is 641 '
	                    'there) and without its offset (the dNBR of an unburned area outside the fire) unless '
	                    '--offset-region gives it. Its classes '
	                    'were calibrated with Landsat TM (30 m) and field plots of 14 fires of the Sierra Nevada of '
	                    'California, mostly in conifer and live oak forests (also pinyon pine and sagebrush), with field '
	                    'data one year after the fire: give a period after about one year after the fire, in the '
	                    'season of the period before')
	_topographic_option(p)
	p.add_argument('--collection', choices=BURN_COLLECTIONS, metavar='ID',
	               help='only with --index RdNBR and --sensor Modis: MODIS/061/MOD09GA (Terra, since 2000-02-24; '
	                    'default) or MODIS/061/MYD09GA (Aqua, since 2002-07-04)')
	p.add_argument('--metric', default='median', help='metric of the images of each period: mean, median, min, max or pN '
	                                                  '(default: median)')
	p.add_argument('--resolution', type=float, help='pixel size in metres (default: that of the data; 1 to 10 km over '
	                                                'more than 100,000 km²)')
	p.add_argument('--csv', help='CSV file of the hectares of each class (dNBR, RdNBR) or of the statistics (RBR)')
	p.add_argument('--out', help='GeoTIFF file, with the bands dnbr, severity, nbr_before and nbr_after (RBR: rbr, '
	                             'dnbr, nbr_before and nbr_after; RdNBR: rdnbr, severity, dnbr, nbr_before and '
	                             'nbr_after)')
	p.add_argument('--perimeter', metavar='FILE',
	               help='vector file (.gpkg, .geojson or .shp) of the perimeter of the burned area: a MultiPolygon of '
	                    'the burned pixels of each feature of the region, to use as the region of other analyses '
	                    '(--region \'{"file": "FILE", "name_field": "region"}\')')
	p.add_argument('--burned-min', type=float, metavar='X',
	               help='with --perimeter: the index from which a pixel is burned (default: dNBR 0.1, RdNBR 0.069; '
	                    'needed with --index RBR, which has no classes)')
	p.add_argument('--min-ha', type=float, metavar='HA',
	               help='with --perimeter: the burned patches of less than HA hectares are left out and the unburned '
	                    'islands of less than HA inside them filled (default 1; 0: all)')
	keep = p.add_mutually_exclusive_group()
	keep.add_argument('--seed', nargs=2, type=float, metavar=('LON', 'LAT'),
	                  help='with --perimeter: only the burned patch nearest to this point (the one that contains it), '
	                       'e.g. the fire alone in a large region')
	keep.add_argument('--largest', action='store_true', help='with --perimeter: only the largest burned patch')
	p.add_argument('--offset-region', metavar='JSON',
	               help='a region (as --region) of unburned land near the fire, of the same vegetation: its median '
	                    'dNBR (the change that is not the fire: phenology, drought, the drying of pastures) is '
	                    'subtracted from the dNBR before the classes, the RBR and the RdNBR (the offset of Miller & '
	                    'Thode 2007 and Parks et al. 2014)')
	p = sub.add_parser('download', help='GeoTIFFs of a recipe of variables over a study area and its ecoregions')
	p.add_argument('recipe', help='YAML file of the recipe (see monitoreo.recipe)')
	p.add_argument('--area', required=True, help='vector file of the study area, or a region as JSON')
	p.add_argument('--layer', help='layer of the vector file, if it has several')
	p.add_argument('--out', required=True, help='folder of the files (those of the ecoregions go to its subfolder ecoregion)')
	p.add_argument('--dry-run', action='store_true', help='show the grids, sizes and number of images, without downloading')
	p.add_argument('--only', choices=('study', 'ecoregion'), help='download only the variables of one grid')
	p.add_argument('--overwrite', action='store_true', help='download again the files that are up to date')
	p.add_argument('--drive', action='store_true', help='export every grid to Google Drive (default: those with drive: true)')
	p.add_argument('--drive-dir', help='local folder of the files exported to Google Drive (default: Google Drive for desktop)')
	p.add_argument('--no-wait', action='store_true', help='do not wait for the export tasks: run again to import them')
	p.add_argument('--tile', type=int, default=512, help='size of the tiles computed by Earth Engine (pixels)')
	p.add_argument('--workers', type=int, default=8, help='tiles computed at the same time')
	p = sub.add_parser('publish', help='publish reports in the static viewer of results (for its administrators)')
	p.add_argument('reports', nargs='*', help='YAML files of the reports (see monitoreo.publish)')
	p.add_argument('--site', help='folder of the site (default: MONITOREO_SITE or ~/MonitorEO/visor)')
	p.add_argument('--remove', action='append', default=[], metavar='ID', help='remove this report from the site')
	p.add_argument('--tags', action='append', default=[], nargs='+', metavar=('ID', 'TAG'),
	               help='give this published report these tags, without publishing it again (none: no tags; it keeps '
	                    'them if published again without tags), e.g. --tags 2026-10-teide-incendio Fire "National parks"')
	p.add_argument('--check', action='store_true', help='check the catalogue and every report of the site')
	p = sub.add_parser('serve', help='the viewer of results on this computer (with range requests, as the web servers)')
	p.add_argument('site', nargs='?', help='folder of the site (default: MONITOREO_SITE or ~/MonitorEO/visor)')
	p.add_argument('--port', type=int, default=8000)
	p = sub.add_parser('projects', help='the Google Cloud projects of your Google account (that of `earthengine '
	                                    'authenticate`) registered in Earth Engine, to give one with --project; Google '
	                                    'does not let MonitorEO list all your projects: those it finds, each one checked '
	                                    'in Earth Engine without computing; --project: one more to check')
	params = p = sub.add_parser('parameters', help='what of a JSON file of parameters of an analysis can be applied '
	                                              '(those that MonitorEO writes next to the files of each result, '
	                                              '<file>.parameters.json, and the other tools save), without computing')
	p.add_argument('file', help='JSON file of parameters ({"monitoreo", "analysis", "parameters"})')
	run = p = sub.add_parser('run', help='compute the analysis of a JSON file of parameters (see monitoreo '
	                                     'parameters): the parameters that cannot be applied are left out and listed')
	p.add_argument('file', help='JSON file of parameters ({"monitoreo", "analysis", "parameters"})')
	p.add_argument('--out', help='stem of the files written (default: <analysis>_<date-time> in this folder): .csv, '
	                             '.png, .tif or .gif, those of the analysis; an animation, as MP4 with an --out ending '
	                             'in .mp4')
	p = sub.add_parser('about', help='what MonitorEO-OBSNEV is, who funds it and how to cite it')
	p.add_argument('--lang', default='en', choices=('en', 'es'))
	p = sub.add_parser('mcp', help='server MCP (stdio) for language models')
	p.add_argument('--no-update', action='store_true', help='do not install the last version of GitHub before starting')
	p = sub.add_parser('assistant', help='AI assistant, in a window of its own (language model of MonitorEO, GLM or '
	                                     'Ollama, and MCP server)')
	p.add_argument('--port', type=int, default=8765)
	p.add_argument('--browser', action='store_true', help='open it in the browser instead of in a window of its own')
	p.add_argument('--no-browser', action='store_true', help='open neither a window nor the browser (only the server)')
	p.add_argument('--no-update', action='store_true', help='do not install the last version of GitHub before starting')
	args = parser.parse_args(_list_args(sys.argv[1:] if argv is None else argv))
	if args.cmd in computes and not (args.cmd == 'areas' and args.landcover):  # what it computes, or its error before
		args.source = _source(args, computes[args.cmd])  # Earth Engine
	elif args.cmd == 'areas':
		if args.variable or args.sensor:
			areas.error('--landcover has its own classes: give no VARIABLE nor --sensor')
		if args.topographic_correction:
			areas.error('--topographic-correction is for the variables of Landsat, not for --landcover')
		if args.snow_ndsi is not None:
			areas.error('--snow-ndsi is for the variables of Sentinel-2 and Landsat, not for --landcover')
		if args.harmonize or args.landsat7:
			areas.error('--harmonize and --landsat7 are for the variables of Landsat, not for --landcover')
		args.source = {}
	if args.cmd == 'info' and '/' in args.variable:  # an ID of Earth Engine: not the list of every variable
		info.error(f'{args.variable} is not a variable of the catalog (monitoreo list): monitoreo asset {args.variable} '
		           'describes an ID of Earth Engine')
	if args.cmd == 'series':  # the options of the chart by day of the year, before Earth Engine
		given = [o for o, v in (('--interannual', args.interannual), ('--other-variable', args.other_variable),
		                        ('--other-sensor', args.other_sensor), ('--ylim', args.ylim),
		                        ('--other-ylim', args.other_ylim)) if v]
		if given and not args.doy:
			computes['series'].error(f"{', '.join(given)}: only with --doy (the chart by day of the year)")
		if (args.other_sensor or args.other_ylim) and not args.other_variable:
			computes['series'].error('--other-sensor and --other-ylim are those of the variable of the right axis: give '
			                         '--other-variable')
	if args.cmd == 'image' and not (args.out or args.rgb):
		image.error('give --out (GeoTIFF of the variable), --rgb (GeoTIFF of its true colour) or both')
	if args.cmd == 'image' and args.rgb and not args.variable:
		image.error('--rgb is only for the variables of the catalog with a true colour (rgb in monitoreo info), not for '
		            'the data of Earth Engine given by its ID')
	if args.cmd == 'burn' and args.sensor == 'Modis' and args.index != 'RdNBR':
		burn.error(f'--sensor Modis is only for --index RdNBR: the {args.index} is computed with Sentinel-2 or Landsat')
	if args.cmd == 'burn' and (args.burned_min is not None or args.min_ha is not None or args.seed or args.largest) \
			and not args.perimeter:
		burn.error('--burned-min, --min-ha, --seed and --largest are for the perimeter of the burned area: give also '
		           '--perimeter FILE')
	if args.cmd == 'burn' and args.perimeter and args.index == 'RBR' and args.burned_min is None:
		burn.error('--index RBR has no classes: give --burned-min, the RBR from which a pixel is burned, for the '
		           'perimeter')
	if args.cmd == 'burn' and args.collection and (args.index, args.sensor) != ('RdNBR', 'Modis'):
		burn.error('--collection is only for --index RdNBR with --sensor Modis: MODIS/061/MOD09GA (Terra, the default) '
		           'or MODIS/061/MYD09GA (Aqua)')

	if args.cmd == 'about':
		print(about.text(args.lang))
		return
	if args.cmd == 'parameters':  # without Earth Engine
		_parameters(args, params)
		return
	if args.cmd == 'run':
		checked = _parameters(args, run, quiet=True)  # its errors before Earth Engine
		from . import services
		services.init(args.project, warn=False)
		try:
			return _run(args, checked, services)
		finally:
			_quota_notice(services)
	if args.cmd == 'serve':
		from . import publish
		publish.serve(args.site, args.port)
		return
	if args.cmd == 'publish':
		return _publish(args)
	if args.cmd == 'assistant':
		return _assistant(args)
	from . import services
	if args.cmd == 'list':
		other = _other_theme(args.theme)
		if other:  # in the words of the command line, not those of the services (describe_asset, collection=...)
			sys.exit(f"ERROR: {other['en']} has no variables of the catalog: {OTHER_THEMES[other['key']]}")
		try:
			rows = services.list_variables(args.sensor, args.text, args.lang, theme=args.theme)
		except ValueError as e:  # an unknown theme, or one of the data of Earth Engine outside the catalog
			sys.exit(f'ERROR: {e}')
		_table(rows, ['ref', 'variable', 'sensor', 'collection', 'resolution_m', 'unit', 'name'])
		return
	if args.cmd == 'info':
		print(json.dumps(services.describe_variable(args.variable, args.sensor), ensure_ascii=False, indent=1))
		return
	if args.cmd == 'classes':  # the table of classes of catalog.json: without Earth Engine
		try:
			rows = services.list_classes(args.variable, args.sensor, args.text, args.limit, args.lang)
		except (KeyError, ValueError) as e:
			sys.exit(f'ERROR: {e}')
		_table(rows, ['code', 'name', 'colour'] + (['group', 'group_name'] if rows and 'group' in rows[0] else []))
		layer = {'variable': args.variable.upper(), 'sensor': args.sensor}
		where = json.dumps([dict(layer, classes=[rows[0]['code'] if rows else 12])])
		print(f"\n{len(rows)} classes | e.g. --where '{where}' or --zones '{json.dumps(layer)}'")
		return
	if args.cmd == 'community':  # the copy of its index in MonitorEO: without Earth Engine
		return _community(args, services)
	if args.cmd == 'datasets':  # the copy of the index of the Earth Engine data catalog: without Earth Engine
		try:
			rows = services.find_datasets(' '.join(args.text), args.start, args.end, args.bbox, args.kind, args.limit)
		except ValueError as e:
			sys.exit(f'ERROR: {e}')
		_table([{k: r.get(k, '') for k in ('id', 'type', 'start', 'end', 'title')} for r in rows],
		       ['id', 'type', 'start', 'end', 'title'])
		print(f'\n{len(rows)} datasets of the Earth Engine data catalog | monitoreo asset ID describes one (its bands, '
		      'units and how to cite it); then compute it with --collection or --image and --band (several with '
		      '--band-reducer)')
		return
	if args.cmd == 'landcover':  # the table of correspondences of catalog.json: without Earth Engine
		return _landcover(args, services)
	if (args.cmd == 'units' and args.level == 3) or args.cmd == 'seas' or \
			(args.cmd == 'burnt' and not args.region):  # the municipalities of Spain, the seas, the fires of a country
		return _compute(args, services)  # (their indexes): without Earth Engine
	if args.cmd == 'mcp':
		_mcp(args)
		return
	if args.cmd == 'projects':  # asks Earth Engine the configuration of each project, without connecting
		return _projects(args, services)
	_data_warnings()
	if args.cmd == 'download':
		try:
			return _download(args, services)
		finally:
			_quota_notice(services)
	services.init(args.project, warn=False)
	try:
		_compute(args, services)
	finally:
		_quota_notice(services)


def _documented(res):
	"""The README and the parameters (monitoreo.parameters) written with the files of a result RES, for its line."""
	return ''.join(f' | {label} {res[k]}' for k, label in (('readme', 'README'), ('parameters', 'parameters'))
	               if res.get(k)) + _manual(res)


def _manual(res):
	"""The sections of the manual (the wiki) that explain the variables of the result RES (its manual), each in a line
	of its own after the line of the result."""
	links = res.get('manual') if isinstance(res, dict) else None
	return ''.join(f"\n  What {link['variable']} is: {link['url']}" for link in links or [] if isinstance(link, dict)
	               and link.get('url'))


def _parameters(args, parser, quiet=False):
	"""What of the JSON file of parameters ARGS.file can be applied (monitoreo.parameters.check): printed, unless
	QUIET; those that cannot, as warnings."""
	from . import parameters
	try:
		checked = parameters.check(args.file)
	except ValueError as e:
		parser.error(str(e))
	if not quiet:
		print(json.dumps({'analysis': checked['analysis'], 'parameters': checked['parameters']}, ensure_ascii=False,
		                 indent=1))
	for p in checked['not_applied']:
		print(f"WARNING: not applied: {parameters.text([p])}", file=sys.stderr)
	if checked.get('note'):
		print(f"NOTE: {checked['note']}", file=sys.stderr)
	return checked


# the files of each output of an analysis (its arguments): extension
OUTPUT_FILES = {'csv': '.csv', 'chart': '.png'}
PATH_EXT = {'map_figure': '.png', 'timelapse': '.gif'}


def _run(args, checked, services):
	"""Compute the analysis of the parameters CHECKED (see _parameters), with its files named after --out."""
	import datetime as dt
	from . import parameters
	analysis = checked['analysis']
	stem = args.out or f"{analysis}_{dt.datetime.now():%Y%m%d-%H%M%S}"
	names = inspect.signature(getattr(services, analysis)).parameters
	outputs = {k: stem + ext for k, ext in OUTPUT_FILES.items() if k in names}
	if 'path' in names:  # an animation: GIF, or MP4 with --out ending in .mp4
		ext = os.path.splitext(stem)[1].lower() if analysis == 'timelapse' else ''
		outputs['path'] = stem if ext in ('.gif', '.mp4') else stem + PATH_EXT.get(analysis, '.tif')
	try:
		res = getattr(services, analysis)(**checked['parameters'], **outputs)
	except (ValueError, KeyError) as e:
		sys.exit(f'ERROR: {e}')
	shown = {k: v for k, v in (res or {}).items() if k not in ('rows', 'profile', 'references', 'credits')
	         and not isinstance(v, (bytes, bytearray))}
	if isinstance(res, dict) and isinstance(res.get('rows'), list):
		shown['rows'] = len(res['rows'])
	print(json.dumps(shown, ensure_ascii=False, indent=1, default=str))
	if checked['not_applied']:
		print(f"WARNING: computed without: {parameters.text(checked['not_applied'])}", file=sys.stderr)


def _projects(args, services):
	"""The Google Cloud projects of the account of `earthengine authenticate` registered in Earth Engine."""
	try:
		found = services.own_projects([args.project] if args.project else [])
	except RuntimeError as e:
		sys.exit(f'ERROR: {e}')
	_table([{k: p[k] or '' for k in ('project', 'name', 'registration')} for p in found['projects']],
	       ['project', 'name', 'registration'])
	print(f"\n{len(found['projects'])} projects registered in Earth Engine"
	      f"{' of ' + found['account'] if found['account'] else ''} | use one with --project PROJECT (or the variable "
	      f"EE_PROJECT). Google does not let MonitorEO list all your projects: if yours is not here, give it anyway. "
	      f"To register one: {found['register']}")


def _data_warnings():
	"""Show the warnings of the periods (the days without images of their data, see monitoreo.coverage) as the other
	warnings of the command line, «WARNING: ...» on the standard error, when they come (before Earth Engine computes),
	instead of as Python warnings."""
	import warnings
	from .coverage import DataDatesWarning
	shown = warnings.showwarning

	def show(message, category, filename, lineno, file=None, line=None):
		if issubclass(category, DataDatesWarning):
			print(f'WARNING: {message}', file=sys.stderr)
		else:
			shown(message, category, filename, lineno, file, line)

	warnings.showwarning = show


def _quota_notice(services):
	"""After a command that computes (also when it fails), warn when Earth Engine has put the project in restricted mode
	(see services.quota_warning: with the shared account, how to compute with your own project)."""
	quota = services.quota_warning()
	if quota:
		own = ' In the command line: --project YOUR_PROJECT.' if services.shared() else ''
		print(f'\nWARNING: {quota}{own}', file=sys.stderr)


def _community(args, services):
	"""The themes of the GEE Community Catalog (services.community_themes) or, with --theme, --text or --kind, its
	images and collections of images (services.community_datasets): from the copy of its index, without Earth
	Engine."""
	if not (args.theme or args.text or args.kind):
		rows = services.community_themes(args.lang)
		_table(rows, ['name', 'datasets'])
		print(f"\n{sum(r['datasets'] for r in rows)} images and collections of images of the GEE Community Catalog | "
		      'monitoreo community --theme NAME lists those of a theme')
		return
	try:
		rows = services.community_datasets(args.theme, args.text, args.kind, args.limit)
	except ValueError as e:  # an unknown theme
		sys.exit(f'ERROR: {e}')
	_table(rows, ['id', 'type', 'title'])
	print(f'\n{len(rows)} datasets of the GEE Community Catalog | monitoreo asset ID describes one (its bands, units '
	      'and how to cite it); then compute it with --collection or --image and --band (several with --band-reducer)')


def _asset(args, services):
	"""What an image or a collection of images of Earth Engine is (services.describe_asset), as JSON."""
	try:
		res = services.describe_asset(args.asset)
	except ValueError as e:  # an ID that this account cannot read, a table or a folder
		sys.exit(f'ERROR: {e}')
	print(json.dumps(res, ensure_ascii=False, indent=1))


def _compute(args, services):
	if args.cmd == 'asset':
		_asset(args, services)
		return
	if args.cmd == 'parks':
		more = {'designation': 'ramsar'} if args.ramsar else {}
		_table(_fmt(services.find_protected_areas(args.text, args.limit, **more)),
		       ['SITE_ID', 'NAME', 'DESIG', 'ISO3', 'REP_AREA'])
		return
	if args.cmd == 'units':
		code = 'ADMIN3_CODE' if args.level == 3 else f'GAUL{args.level}_CODE'
		try:
			units = services.find_admin_units(args.text, args.level, args.country, args.limit)
		except ValueError as e:  # level 3 of a country that is not Spain
			sys.exit(f'ERROR: {e}')
		_table(_fmt(units), [code, 'DISP_EN', 'ISO3_CODE'])
		return
	if args.cmd == 'burnt':
		from . import references
		region = json.loads(args.region) if args.region else None
		try:
			rows = services.find_burnt_areas(region, args.country, args.start, args.end, args.min_area, args.limit)
		except ValueError as e:
			sys.exit(f'ERROR: {e}')
		_table(_fmt(rows), ['effis_id', 'firedate', 'finaldate', 'area_ha', 'country', 'province', 'commune'])
		print(f'\n{len(rows)} burnt areas of EFFIS | use one as --region \'{{"effis_id": ID}}\' | cite: '
		      + '; '.join(r['text'] for r in references.cite('find_burnt_areas', {'region': region})['references']))
		return
	if args.cmd == 'seas':
		seas = [dict(s, BOUNDS=' '.join(f'{b:g}' for b in s['BOUNDS']))
		        for s in services.find_seas(args.text, args.limit)]
		_table(_fmt(seas), ['MRGID', 'NAME', 'AREA_KM2', 'BOUNDS'])
		if not seas:
			print('No sea with that name: try its English name (e.g. Alboran, Biscay, Mediterranean)', file=sys.stderr)
		return
	if args.cmd in ('trend', 'compare'):
		_trend_or_compare(args, services)
		return
	if args.cmd == 'burn':
		_burn(args, services)
		return
	if args.cmd == 'timelapse':
		_timelapse(args, services)
		return
	if args.cmd == 'areas':
		_areas(args, services)
		return
	if args.cmd == 'transect':
		_transect(args, services)
		return
	if args.cmd == 'figure':
		try:
			res = services.map_figure(json.loads(args.region), start=args.start, end=args.end, metric=args.metric,
			                          temporal=args.temporal, interannual=args.interannual, vmin=args.vmin,
			                          vmax=args.vmax, path=args.out, title=args.title, dpi=args.dpi, where=_where(args),
			                          percentiles=args.percentiles, **args.source)
		except ValueError as e:
			sys.exit(_error(e, args))
		colours = f"{len(res['classes'])} classes" if res.get('classes') is not None else \
			f"colours {res['min']:.4g} to {res['max']:.4g} {res['unit']}".rstrip() + _stretch(res)  # categorical: classes
		print(f"{res['file']}: {res['name']} | {colours}" + _documented(res))
		return
	progress = lambda d, t: print(f'  {d}/{t} steps', file=sys.stderr)  # noqa: E731
	if args.cmd == 'image':
		_image(args, services)
		return
	if args.cmd == 'stats':
		_stats(args, services)
		return
	if args.cmd == 'count':
		_count(args, services, progress)
		return
	if args.cmd == 'recovery':
		_recovery(args, services, progress)
		return
	if args.cmd == 'recovery-map':
		try:
			res = services.recovery_map(json.loads(args.region), args.variable, args.sensor, args.start, args.end,
			                            event=args.event, metric=args.metric, season=args.season,
			                            resolution=args.resolution, reference_years=args.reference_years,
			                            equilibrium=args.equilibrium, path=args.out, where=_where(args),
			                            progress=lambda d, t, what='years': print(f'  {d}/{t} {what}', file=sys.stderr))
		except ValueError as e:
			sys.exit(f'ERROR: {e}')
		s = res['summary']
		print(f"{s['pixels']:,} pixels with metrics" + (
			f"; recovered (back in the reference): {100 * (s['recovered_share'] or 0):.0f} %"
			+ (f", in a median of {s['RRT_median']:g} years" if s['RRT_median'] is not None else '')
			+ (f"; median impact {s['impact_pct_median']:g} %" if s['impact_pct_median'] is not None else '')
			+ (f", recovered {s['recovered_pct_median']:g} %" if s['recovered_pct_median'] is not None else '')
			if s['pixels'] else ': none has a reference and a year after the event'))
		print(f"\n{res['title']} | GeoTIFF {res['file']} (bands {', '.join(res['bands'])}) | yearly {res['yearly']}"
		      + _documented(res))
		return
	if args.cmd == 'ring':
		try:
			res = services.control_ring(json.loads(args.region), args.gap, args.width,
			                            json.loads(args.exclude) if args.exclude else None,
			                            json.loads(args.within) if args.within else None, args.match, path=args.out)
		except ValueError as e:
			sys.exit(_error(e, args))
		for name, ha in res['ha'].items():
			print(f'{name}: {ha:,.1f} ha')
		print('matched: ' + ('; '.join(f'{k} {v[0]:g} to {v[1]:g}' for k, v in res['match'].items()) or 'nothing'))
		print(f"\n{res['title']} | {res['file']} | region: {{\"file\": \"{res['file']}\", \"name_field\": \"region\"}} "
		      f"with --where '{json.dumps(res['where'])}'" + _documented(res))
		return
	try:
		res = services.time_series(json.loads(args.region), start=args.start, end=args.end, step=args.step,
		                           metric=args.metric, stat=args.stat, scale=args.scale, csv=args.csv, chart=args.png,
		                           progress=progress, where=_where(args), doy=args.doy, interannual=args.interannual,
		                           other_variable=args.other_variable, other_sensor=args.other_sensor, ylim=args.ylim,
		                           other_ylim=args.other_ylim, min_coverage=args.min_coverage, ring=_ring(args),
		                           **args.source)
	except ValueError as e:  # e.g. an image given as a collection, a unit that is not UDUNITS
		sys.exit(_error(e, args))
	files = (f" | CSV {res['csv']}" if res['csv'] else '') + (f" | chart {res['chart']}" if res['chart'] else '')
	if args.doy and (args.interannual or args.other_variable):  # the seasonal profile: what the chart and the CSV have
		_profile(res, services, files)
		return
	_table(_fmt(res['rows']), ['region', 'date', 'value', 'n_pixels', 'n_images']
	       + (['coverage'] if args.min_coverage else []))
	print(f"\n{res['title']} | scale {res['scale']:g} m" + (f" | unit {res['unit']}" if res['unit'] else '')  # none given
	      + files
	      + _manual(res))


def _recovery(args, services, progress):
	"""The recovery metrics after a disturbance (services.recovery_metrics): a row per series."""
	try:
		res = services.recovery_metrics(json.loads(args.region), start=args.start, end=args.end, event=args.event,
		                                step=args.step, metric=args.metric, stat=args.stat, scale=args.scale,
		                                affected=args.affected, control=args.control,
		                                reference_years=args.reference_years, equilibrium=args.equilibrium,
		                                min_coverage=args.min_coverage, csv=args.csv, chart=args.png, progress=progress,
		                                ring=_ring(args),
		                                where=_where(args), **args.source)
	except ValueError as e:
		sys.exit(_error(e, args))
	_table(_fmt(res['rows']), ['series', 'direction', 'S95', 'impact_pct', 'DIT_years', 'RRT_years', 'RET_years',
	                           'recovered_pct'])
	files = (f" | CSV {res['csv']}" if res['csv'] else '') + (f" | chart {res['chart']}" if res['chart'] else '')
	print(f"\n{res['title']} | scale {res['scale']:g} m | years from the event; RRT empty: not recovered yet" + files
	      + _manual(res))


def _count(args, services, progress):
	"""The images and valid observations of a variable per step (services.image_count): a row per step and region."""
	try:
		res = services.image_count(json.loads(args.region), start=args.start, end=args.end, step=args.step,
		                           scale=args.scale, csv=args.csv, chart=args.png, progress=progress, where=_where(args),
		                           **args.source)
	except ValueError as e:
		sys.exit(_error(e, args))
	_table(_fmt(res['rows']), services.IMAGE_COUNT_COLUMNS)
	files = (f" | CSV {res['csv']}" if res['csv'] else '') + (f" | chart {res['chart']}" if res['chart'] else '')
	print(f"\n{res['title']} | scale {res['scale']:g} m | observations: valid images per pixel (mean over the pixels "
	      f"with data); coverage: fraction of the region with data" + files + _manual(res))


def _range_label(res, default='p1-p99'):
	"""The range of the colours of RES in a few words: pLOW-pHIGH (its percentiles), 'given' (vmin and vmax) or
	DEFAULT (a result without stretch)."""
	st = res.get('stretch') if isinstance(res.get('stretch'), dict) else {}
	if st.get('method') == 'given':
		return 'colours given'
	if st.get('method') == 'mixed':  # one end given, the other from a percentile (or the catalog)
		lo, hi = st.get('percentiles') or (None, None)
		other = 'catalog' if lo is None else f'p{hi:g}' if st.get('given') == 'min' else f'p{lo:g}'
		return f'vmin given-{other}' if st.get('given') == 'min' else f'{other}-vmax given'
	if st.get('percentiles'):
		lo, hi = st['percentiles']
		return f'p{lo:g}-p{hi:g}'
	return default


def _stretch(res):
	"""How the colours of RES were stretched, after ' | ' ('' without it)."""
	st = res.get('stretch')
	return f" ({st['text']})" if isinstance(st, dict) and st.get('text') else ''


def _axis(lim):
	"""The range LIM of a y axis, (min, max) or None, in words."""
	return f'{lim[0]:g} to {lim[1]:g}' if lim else 'from the data'


def _profile(res, services, files):
	"""The table of a seasonal profile by day of the year (services.time_series with --doy and --interannual or
	--other-variable), its title and, for each variable, its pixel size, unit and y axis; then FILES (CSV and chart)."""
	names = res.get('variables') or []
	two = len(names) > 1
	_table(_fmt(res['profile']), [c for c in services.timeseries.PROFILE_COLUMNS if c != 'variable' or two])
	units, scales = res.get('units') or {}, res.get('scales') or {}
	if two:
		scale = ', '.join(f'{n} {scales[n]:g} m' if scales.get(n) else n for n in names)
		unit = ', '.join(f"{n} {units.get(n) or '(no unit)'}" for n in names)
		what = (f" | scale {scale} | units {unit} | left y axis ({names[0]}) {_axis(res.get('ylim'))}, right y axis "
		        f"({names[1]}) {_axis(res.get('other_ylim'))}")
	else:
		what = (f" | scale {res['scale']:g} m" + (f" | unit {res['unit']}" if res['unit'] else '')
		        + f" | y axis {_axis(res.get('ylim'))}")
	print(f"\n{res['title']}{what}{files}"
	      + _manual(res))


def _image(args, services):
	"""GeoTIFFs of the map of a variable (services.download_image, --out) and of the true colour of the same images
	(services.download_rgb, --rgb), or of one of them: with both, the true colour gets the pixel size of the map, so
	that both are on the same grid, and what has no true colour is refused before computing the map."""
	from . import variable as variables
	tiles = lambda d, t: print(f'  {d}/{t} tiles', file=sys.stderr)  # noqa: E731
	try:
		region = json.loads(args.region)
		same = dict(args.source, start=args.start, end=args.end, metric=args.metric, temporal=args.temporal,
		            interannual=args.interannual, where=_where(args))
		resolution = args.resolution
		if args.out:
			if args.rgb:  # its refusals (variable, metric) before Earth Engine computes the map
				variables.check_rgb(services.make_spec(**same))
			res = services.download_image(region, resolution=resolution, path=args.out, progress=tiles, vmin=args.vmin,
			                              vmax=args.vmax, percentiles=args.percentiles,
			                              **same)
			images = 'fixed image' if res.get('images') is None else f"{res['images']} images"  # no dates: none
			if res.get('classes') is not None:  # a categorical layer: the classes in the file
				print(f"{res['file']}: {res['name']} | {res['grid']['width']} x {res['grid']['height']} pixels of "
				      f"{res['resolution']:g} m | {len(res['classes'])} classes: "
				      + '; '.join(c['label'] for c in res['classes'][:10]) + ('...' if len(res['classes']) > 10 else '')
				      if res['classes'] else f"{res['file']}: no valid pixel")
			else:
				print(f"{res['file']}: {res['name']} | {res['grid']['width']} x {res['grid']['height']} pixels of "
				      f"{res['resolution']:g} m | {images} | {_range_label(res)} {res['min']:.4g} to {res['max']:.4g} "
				      f"{res['unit']}".rstrip() if res['min'] is not None else f"{res['file']}: no valid pixel")
			resolution = res['resolution']
		if args.rgb:
			alone = not args.out  # the range given is that of the true colour only without the map of the variable
			res = services.download_rgb(region, resolution=resolution, path=args.rgb, progress=tiles,
			                            percentiles=args.percentiles if alone else None,
			                            vmin=args.vmin if alone else None, vmax=args.vmax if alone else None, **same)
			print(f"{res['file']}: {res['name']} | {res['grid']['width']} x {res['grid']['height']} pixels of "
			      f"{res['resolution']:g} m | {res['images']} images | bands {', '.join(res['bands'])} | reflectance "
			      f"{res['min']:.4g} to {res['max']:.4g} ({_range_label(res, 'p2-p98')})" if res['min'] is not None
			      else f"{res['file']}: no valid pixel")
	except ValueError as e:
		sys.exit(_error(e, args))


def _stats(args, services):
	"""Statistics of the map of a variable over each feature of the region (services.region_stats): any of mean,
	median, min, max, std, cv (coefficient of variation, %) and pN, for any variable, also the fixed layers."""
	stats = [s.strip() for s in str(args.stats).split(',') if s.strip()] if args.stats else None  # those of the service
	try:
		res = services.region_stats(json.loads(args.region), start=args.start, end=args.end, metric=args.metric,
		                            temporal=args.temporal, interannual=args.interannual, stats=stats, scale=args.scale,
		                            where=_where(args), zones=json.loads(args.zones) if args.zones else None,
		                            csv=args.csv, chart=args.png, **args.source)
	except ValueError as e:
		sys.exit(_error(e, args))
	shown = list(res.get('stats') or stats or [])
	if any('mode_label' in r for r in res['rows']):  # a categorical layer: the name of the majority class too
		shown.insert(shown.index('mode') + 1 if 'mode' in shown else len(shown), 'mode_label')
	_table(_fmt(res['rows']), ['region'] + (['zone_label'] if args.zones else []) + shown + ['n_pixels'])
	cv = ' | cv in %' if any(str(s).lower() == 'cv' for s in res.get('stats') or stats or []) else ''
	print(f"\n{res['title']} | scale {res['scale']:g} m" + (f" | unit {res['unit']}" if res['unit'] else '') + cv
	      + _manual(res))


def _areas(args, services):
	"""Hectares and % of each class (services.area_by_class): of a land cover map, of the map of a variable cut at
	--breaks or of its trend on each pixel."""
	try:
		res = services.area_by_class(json.loads(args.region), start=args.start, end=args.end, metric=args.metric,
		                             temporal=args.temporal, interannual=args.interannual, landcover=args.landcover,
		                             year=args.year, breaks=args.breaks, trend=args.trend, step=args.step,
		                             part=args.part, alpha=args.alpha, test=args.test, scale=args.scale, csv=args.csv, chart=args.png,
		                             where=_where(args), other_year=args.other_year, **args.source)
	except ValueError as e:
		sys.exit(_error(e, args))
	if res['mode'] == 'transitions':
		_table([{k: (f'{v:.1f}' if k in ('ha', 'percent') and isinstance(v, float) else v) for k, v in r.items()}
		        for r in res['by_landcover']], ['region', 'from_label', 'to_label', 'ha', 'percent'])
		print()
		for region, ha in res['changed_ha'].items():
			print(f"{region}: changed {ha:.1f} ha, unchanged {res['unchanged_ha'][region]:.1f} ha (by class of the map)")
		print(f"\n{res['title']} | pixels of {res['scale']:g} m | the broad land covers; every pair of classes in the CSV"
		      + (f" | CSV {res['csv']}" if res.get('csv') else '') + (f" | Sankey {res['chart']}" if res.get('chart')
		                                                              else '')
		      + _manual(res))
		return
	cols = ['region', 'class', 'label'] + (['landcover'] if res['mode'] == 'landcover' else []) + \
		(['group_label'] if res.get('by_group') is not None else []) + ['ha', 'percent']  # the biome of an ecoregion
	_table([{k: (f'{v:.1f}' if k in ('ha', 'percent') and isinstance(v, float) else v) for k, v in r.items()}
	        for r in res['rows'] if r.get('ha')], cols)
	print(f"\n{res['title']} | pixels of {res['scale']:g} m | % of the area with classes"
	      + (f" | CSV {res['csv']}" if res.get('csv') else '') + (f" | chart {res['chart']}" if res.get('chart') else '')
	      + _documented(res))


def _timelapse(args, services):
	"""Animation of a variable over the region (services.timelapse): the GIF or the MP4, its frames and its colours."""
	try:
		res = services.timelapse(json.loads(args.region), start=args.start, end=args.end, step=args.step,
		                         metric=args.metric, vmin=args.vmin, vmax=args.vmax, fps=args.fps,
		                         dimensions=args.dimensions, path=args.out, where=_where(args),
		                         percentiles=args.percentiles, same_colours=args.same_colours,
		                         progress=lambda d, t: print(f'  {d}/{t} frames', file=sys.stderr), **args.source)
	except ValueError as e:
		sys.exit(_error(e, args))
	_table([{'frame': i, 'label': f['label'], 'images': f['images'],
	         'colours': f"{f['min']:.4g} to {f['max']:.4g}" if f.get('min') is not None else ''}
	        for i, f in enumerate(res['frames'], 1)], ['frame', 'label', 'images', 'colours'])
	print(f"\n{res['file']}: {res['name']} | {res['n_frames']} frames, {res['fps']:g} per second | colours "
	      f"{res['min']:.4g} to {res['max']:.4g} {res['unit']}".rstrip() + _stretch(res)
	      + _documented(res))
	if res.get('note'):
		print(res['note'], file=sys.stderr)


def _transect(args, services):
	"""Profile of a variable along a line (services.transect): the value and the elevation of each segment."""
	try:
		res = services.transect(args.line, start=args.start, end=args.end, metric=args.metric, temporal=args.temporal,
		                        interannual=args.interannual, spacing=args.spacing, points=args.points, csv=args.csv,
		                        chart=args.png, where=_where(args), **args.source)
	except ValueError as e:
		sys.exit(_error(e, args))
	_table(_fmt(res['rows']), ['distance_m', 'value', 'elevation', 'lon', 'lat'])
	print(f"\n{res['title']} | segments of {res['spacing']:.4g} m | elevation in m"
	      + (f" | unit {res['unit']}" if res['unit'] else '') + (f" | CSV {res['csv']}" if res.get('csv') else '')
	      + (f" | chart {res['chart']}" if res.get('chart') else '')
	      + _manual(res))


def _fmt(rows, digits=4):
	return [{k: (f'{v:.{digits}g}' if isinstance(v, float) else v) for k, v in r.items()} for r in rows]


def _trend_or_compare(args, services):
	progress = lambda d, t: print(f'  {d}/{t} steps', file=sys.stderr)  # noqa: E731
	try:
		region = json.loads(args.region)
		same = dict(args.source, start=args.start, end=args.end, step=args.step, metric=args.metric, stat=args.stat,
		            scale=args.scale, csv=args.csv, chart=args.png, progress=progress, where=_where(args),
		            min_coverage=args.min_coverage)
		if args.cmd == 'trend':
			res = services.trend_table(region, test=args.test, **same)
		else:
			res = services.compare_series(region, other_start=args.other_start, other_end=args.other_end, **same)
	except ValueError as e:  # e.g. an image given as a collection, a unit that is not UDUNITS
		sys.exit(_error(e, args))
	if args.cmd == 'trend':
		_table(_fmt(res['rows']), ['region', 'key', 'label', 'n', 'tau', 'z', 'p_value', 'significant', 'slope',
		                           'intercept'])
		extra = f" | slope in {res['unit']} / year" if res['unit'] else ' | slope per year'  # no unit given
	else:
		_table(_fmt(res['profile']), ['region', 'key', 'label', 'reference', 'other', 'difference', 'n_reference',
		                              'n_other'])
		extra = ''
	print(f"\n{res['title']} | scale {res['scale']:g} m{extra}"
	      + (f" | CSV {res['csv']}" if res['csv'] else '') + (f" | chart {res['chart']}" if res['chart'] else '')
	      + _manual(res))


def _burn(args, services):
	"""Burn severity of a fire (services.burn_severity): the hectares of each class of the USGS and the burned area of
	each region (dNBR), the statistics of the RBR, or the hectares of each class of Miller & Thode 2007, the changed
	area of each region and the statistics of the RdNBR, and the CSV, GeoTIFF and README written."""
	from . import fire
	try:
		res = services.burn_severity(json.loads(args.region), args.sensor, args.start, args.end, args.other_start,
		                             args.other_end, args.metric, resolution=args.resolution, path=args.out,
		                             csv=args.csv, index=args.index, where=_where(args), collection=args.collection,
		                             progress=lambda d, t: print(f'  {d}/{t} tiles', file=sys.stderr),
		                             perimeter=args.perimeter, burned_min=args.burned_min, min_ha=args.min_ha,
		                             seed=args.seed, largest=args.largest,
		                             offset_region=json.loads(args.offset_region) if args.offset_region else None,
		                             **_topographic(args))
	except ValueError as e:
		sys.exit(f'ERROR: {e}')

	def cells(rows):  # hectares with a decimal, the rest with 4 digits, and nothing for the open ends of the classes
		return [{k: '' if v is None else f'{v:.1f}' if k == 'ha' else f'{v:.4g}' if isinstance(v, float) else v
		         for k, v in r.items()} for r in rows]
	stats = services.RBR_COLUMNS  # region, mean, median, std, cv (%), p10, p90, min, max and ha
	if res['index'] == 'RBR':
		_table(cells(res['stats']), stats)
	elif res['index'] == 'RdNBR':
		_table(cells(res['classes']), ['region', 'class', 'label', 'rdnbr_min', 'rdnbr_max', 'ha'])
		print()
		for region, ha in (res.get('burned_ha') or {}).items():  # unchanged is not unburned (Miller & Thode 2007)
			print(f'{region}: changed area (RdNBR >= {fire.RDNBR_BURNED:g}) {ha:.1f} ha')
		if res.get('stats'):
			print()
			_table(cells(res['stats']), stats)
	else:
		_table(cells(res['classes']), ['region', 'class', 'label', 'dnbr_min', 'dnbr_max', 'ha'])
		print()
		for region, ha in res['burned_ha'].items():
			print(f'{region}: burned area (dNBR >= {fire.BURNED:g}) {ha:.1f} ha')
	if res.get('offset') is not None:
		print(f"\ndNBR offset (median of --offset-region, subtracted): {res['offset']:.4g}")
	if res.get('perimeter'):
		print()
		for region, ha in res['perimeter_ha'].items():
			print(f"{region}: perimeter of the burned area ({res['index']} >= {res['burned_min']:g}, patches and "
			      f"islands of at least {res['min_ha']:g} ha) {ha:.1f} ha in {res['perimeter_patches'][region]} patches"
			      + (f" ({res['perimeter_kept']})" if res.get('perimeter_kept') else ''))
	print(f"\n{res['title']} | pixels of {res['scale']:g} m"
	      + (f" | CSV {res['csv']}" if res.get('csv') else '') + (f" | GeoTIFF {res['file']}" if res.get('file') else '')
	      + (f" | perimeter {res['perimeter']}" if res.get('perimeter') else '')
	      + _documented(res)
	      + _manual(res))


def _publish(args):
	from . import publish, services
	try:
		if not (args.reports or args.remove or args.tags or args.check):
			publish.install_viewer(args.site)
			publish.update_catalog(args.site)
			print(f'Updated the viewer and the catalogue of {publish.site_folder(args.site)}')
		for rid in args.remove:
			res = services.remove_report(rid, args.site)
			print(f"Removed {rid} from {res['site']}")
		for rid, *tags in args.tags:
			res = services.tag_report(rid, tags, args.site)
			print(f"Tags of {rid}: {', '.join(res['tags']) or 'none'}")
		for path in args.reports:
			res = services.publish_report(path, args.site)
			for r in res['reports']:
				print(f"Published {r['id']}: {r['title']}")
	except (ValueError, RuntimeError, FileNotFoundError) as e:
		sys.exit(f'ERROR: {e}')
	problems = services.check_site(args.site)
	for p in problems:
		print(f'  {p}', file=sys.stderr)
	if problems:
		sys.exit(f'ERROR: {len(problems)} problems in the site')
	print(f'Site {publish.site_folder(args.site)} is right; see it with: monitoreo serve {args.site or ""}'.rstrip())


def _mcp(args):
	"""Start the MCP server, after installing the last version of GitHub (then it starts again, with that version)."""
	if not args.no_update:
		from . import update
		if update.ensure_latest('mcp,plot') == 'updated':
			cmd = [sys.executable, '-m', 'monitoreo.cli', 'mcp', '--no-update']
			if os.name == 'nt':  # no exec on Windows: run it with the same stdin and stdout
				sys.exit(subprocess.call(cmd))
			os.execv(sys.executable, cmd)
	from . import mcp_server
	mcp_server.main()


def _assistant(args):
	"""Start the assistant, after installing the last version of GitHub (then it starts again, with that version);
	if it is open already, only open it."""
	if sys.stderr is None or sys.stdout is None:  # pythonw.exe (Windows) or an app of macOS: the messages to a file
		folder = os.path.expanduser(os.environ.get('MONITOREO_OUTPUT') or '~/MonitorEO')
		os.makedirs(folder, exist_ok=True)
		sys.stdout = sys.stderr = open(os.path.join(folder, 'assistant-output.log'), 'a', encoding='utf-8', buffering=1)
	if not args.no_update and not _listening(args.port):
		from . import update
		window = not (args.browser or args.no_browser)
		if (_update_in_window() if window else update.ensure_latest('assistant')) in ('updated', 'shown'):
			cmd = [sys.executable] + (['-s'] if sys.flags.no_user_site else []) + \
			      ['-m', 'monitoreo.cli', 'assistant', '--no-update', '--port', str(args.port)] + \
			      (['--browser'] if args.browser else []) + (['--no-browser'] if args.no_browser else [])
			if os.name == 'nt':
				sys.exit(subprocess.call(cmd))
			os.execv(sys.executable, cmd)
	from . import assistant
	assistant.run(args.port, browser=not args.no_browser, window=not (args.browser or args.no_browser))


def _listening(port):
	import socket
	with socket.socket() as s:
		return s.connect_ex(('127.0.0.1', port)) == 0


UPDATING = '''<!doctype html><meta charset="utf-8"><body style="font: 15px system-ui, sans-serif; margin: 28px;
color: #1f2d27; background: #fff"><h2 style="margin: 0 0 12px; color: #2e6b4f">Updating MonitorEO…</h2>
<p>There is a new version on GitHub: it is downloaded and installed (a minute) and then the assistant opens.</p>'''


def _update_in_window():
	"""update.ensure_latest('assistant') with a small window that says so while it installs a new version (an
	assistant opened without a terminal shows nothing else meanwhile): 'shown' if that window was shown, as then the
	assistant has to start in another process (pywebview starts once in each)."""
	from . import update
	try:
		import webview
	except Exception:  # without pywebview the assistant opens in the browser: as in a terminal
		return update.ensure_latest('assistant')
	installing, done, out = threading.Event(), threading.Event(), {}

	def work():
		try:
			out['result'] = update.ensure_latest('assistant', installing=installing.set)
		finally:
			done.set()
			installing.set()
	threading.Thread(target=work, daemon=True).start()
	installing.wait()
	if done.is_set():  # the last version, or no connection: nothing to show
		return out.get('result', 'offline')
	try:
		win = webview.create_window('MonitorEO AI Assistant', html=UPDATING, width=520, height=200, resizable=False)
		webview.start(lambda: (done.wait(), win.destroy()))
	except Exception as e:
		print(f'WARNING: cannot show the window of the update ({type(e).__name__}: {e})', file=sys.stderr)
	done.wait()
	return 'shown'


def _download(args, services):
	from . import recipe
	try:
		rec = recipe.read(args.recipe)
		services.init(args.project or rec.get('project') or None, warn=False)
		area = json.loads(args.area) if args.area.lstrip().startswith('{') else args.area

		def progress(file, done, total):
			print(f'\r  {file}: {done}/{total} tiles', end='\n' if done == total else '', file=sys.stderr, flush=True)

		res = services.download_variables(rec, area, args.out, args.layer, only=args.only, dry_run=args.dry_run,
		                                  overwrite=args.overwrite, drive_all=args.drive, drive_dir=args.drive_dir,
		                                  wait=not args.no_wait, tile=args.tile, workers=args.workers,
		                                  log=None if args.dry_run else lambda m: print(m, flush=True),
		                                  progress=progress)
	except (ValueError, RuntimeError) as e:
		sys.exit(f'ERROR: {e}')
	if args.dry_run:
		print(f"Study area: {res['area']}")
		for name, g in res['grids'].items():
			print(f"{name} grid: {g['crs']}, {g['resolution']:g} m, {g['width']} x {g['height']} pixels, "
			      f"{g['mb_per_variable']:g} MB per variable")
		for e in res['ecoregions']:
			print(f"  ecoregion {e['ECO_ID']}: {e['ECO_NAME']} ({e['BIOME_NAME']})")
		for f in res['files']:
			n = f['images']
			print(f"  {f['file']}: {'fixed image' if n is None else str(n) + ' images'}"
			      + (f" (pixel filters: {', '.join(f['pixel_filters']) or 'none'})" if 'pixel_filters' in f else ''))
		return
	if res['done']:
		print(f"\nDone: {', '.join(res['folders'].values())} (NoData -9999).")
	else:
		sys.exit(1)


if __name__ == '__main__':
	main()
