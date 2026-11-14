"""Command line of MonitorEO:

    monitoreo list [--sensor S] [--text T]           variables of the catalog
    monitoreo info VARIABLE [--sensor S]             everything about a variable
    monitoreo parks TEXT [--ramsar]                  protected areas of WDPA with TEXT in their name
    monitoreo units TEXT [--level 1|2] [--country ISO3]   administrative units of FAO GAUL 2025 by name
    monitoreo series VARIABLE --sensor S --region JSON --start D --end D [--step monthly] [--csv F] [--png F]
    monitoreo image VARIABLE --sensor S --region JSON --start D --end D [--out F.tif] [--rgb F.tif] [--metric median]
                    [--resolution M]                 GeoTIFF of the map of a variable aggregated in time (--out), of the
                                                     true colour of the same images (--rgb: bands red, green and blue)
                                                     or both, on the same grid
    monitoreo trend VARIABLE --sensor S --region JSON --start D --end D [--step annual|monthly|16-day] [--csv F]
                                                     seasonal trends (Mann-Kendall and Sen) of each part of the year
    monitoreo compare VARIABLE --sensor S --region JSON --start D --end D --other-start D --other-end D [--step]
                                                     a reference period against another, by part of the year
    monitoreo series --collection ID --band B [--band-scale F] [--band-offset F] [--unit U] --region JSON ...
                                                     the same with any collection of images of Earth Engine by its ID,
                                                     instead of VARIABLE and --sensor (also image, trend and compare);
                                                     image also takes --image ID (a fixed image, without dates) and
                                                     --terrain slope|aspect (in degrees: its unit is then degree)
    monitoreo asset ID                              what an image or collection of Earth Engine is (type, bands,
                                                     units, scale, dates, how to cite it), to give it with --collection
                                                     or --image and --band
    monitoreo community [--theme T] [--text T] [--kind image|image_collection] [--limit N] [--lang es]
                                                     the themes of the GEE Community Catalog or, with --theme, --text
                                                     or --kind, its images and collections of images (ID, type, title)
    monitoreo burn --sensor S --region JSON --start D --end D --other-start D --other-end D
                   [--index dNBR|RBR|RdNBR] [--collection ID] [--csv F] [--out F.tif]
                                                     burn severity of a fire: hectares of the classes of the USGS
                                                     (dNBR) or of Miller & Thode 2007 (RdNBR, also with Modis), or
                                                     statistics of the RBR, before (start to end) and after
                                                     (other-start to other-end) the fire
    monitoreo download RECIPE --area FILE|JSON --out FOLDER [--dry-run]   GeoTIFFs of a recipe of variables
    monitoreo publish REPORT.yaml [...] [--site S]   publish reports in the static viewer of results (administrators)
    monitoreo publish [--remove ID] [--check] [--site S]   remove a report, or check the site; with nothing else,
                                                     update its viewer (after updating monitoreo) and its catalogue
    monitoreo serve [SITE] [--port 8000]             the viewer of results on this computer
    monitoreo eecu [--limit H|TIER] [--lang es]      EECUs of Earth Engine spent this month: your research EECUs with
                                                     the shared account of MonitorEO, or the quota of your project
    monitoreo about [--lang es]                      what MonitorEO-OBSNEV is, who funds it and how to cite it
    monitoreo mcp [--no-update]                      server MCP (stdio) for language models, at the last version
                                                     of GitHub (installed when it starts, if needed)
    monitoreo assistant [--port 8765] [--browser] [--no-update]   chat for managers in a window of its own (or
                                                     the browser), with a language model of Ollama and the MCP server,
                                                     at the last version of GitHub

The region is a JSON dictionary, e.g. '{"wdpa_id": 555513}', '{"admin2": 141938}', '{"country": "ESP"}',
'{"island_at": [2.9, 39.6]}' or '{"bbox": [-3.5, 37, -3, 37.2]}'. The Earth Engine
project is --project, the variable EE_PROJECT or (download) project: of the recipe, with the Google account of
`earthengine authenticate`; without one, it computes with the shared account of MonitorEO, where each user has research
EECUs for each month, only for research. The commands that compute warn when less than 10 % of the EECUs of the month
are left. The recipe of download is a YAML
file with the variables, their metrics and the pixel sizes of the study area and of its ecoregions (see
monitoreo.recipe). The report of publish is a YAML file with its texts and the results of an analysis (see
monitoreo.publish); the site is --site, the variable MONITOREO_SITE or ~/MonitorEO/visor.
"""

import argparse
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
              'the maps and the land covers; see the wiki, Concepts)')


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


SENSOR_HELP = 'the sensor of VARIABLE, e.g. Sentinel-2 (monitoreo list gives those of each variable)'
# the options of the data of Earth Engine given by its ID, instead of VARIABLE and --sensor (see monitoreo asset)
SOURCE_OPTIONS = {'image': '--image', 'band': '--band', 'band_scale': '--band-scale', 'band_offset': '--band-offset',
                  'unit': '--unit', 'terrain': '--terrain'}


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
	                              ' (one; monitoreo asset ID lists them)')
	p.add_argument('--band-scale', type=float, metavar='F', help='factor of the stored values of the band (e.g. 0.1)')
	p.add_argument('--band-offset', type=float, metavar='F',
	               help='what is added to the values of the band after --band-scale')
	p.add_argument('--unit', help="unit of the values (after --band-scale and --band-offset) in UDUNITS, e.g. mm, degC, "
	                              "'kg m-2', 'mm day-1' or 1 (dimensionless)" +
	                              ('; with --terrain, none or degree' if image else ''))
	if image:
		p.add_argument('--terrain', choices=('slope', 'aspect'),
		               help='the slope or the aspect of the band of --image (e.g. of a DEM), in degrees (its unit is '
		                    'then degree: give no --unit, or degree, not that of the band)')


# the themes of the data of Earth Engine outside the catalog (catalog.OTHER_THEMES), with the commands and options of
# the command line
OTHER_THEMES = {
	'earth_engine': 'any image or collection of images of Earth Engine by its ID: monitoreo asset ID describes it (its '
	                'bands, units and dates); then compute it with --collection (or --image, in monitoreo image) and '
	                '--band',
	'community': 'the datasets of the GEE Community Catalog by its own themes: monitoreo community lists its themes '
	             'and, with --theme or --text, their datasets; monitoreo asset ID describes one; then compute it with '
	             '--collection (or --image, in monitoreo image) and --band'}


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
		text += (f'; in the command line, --image {asset} instead of --collection' if args.cmd == 'image' else
		         f"; in the command line, monitoreo image --image {asset} --band {args.source.get('band')} (a GeoTIFF)")
	return text


def _source(args, parser):
	"""The data that a command computes, as the keywords of services: VARIABLE and --sensor (a variable of the catalog;
	--collection, one of its collections), or --collection or --image and --band (any data of Earth Engine by its ID),
	with --band-scale, --band-offset, --unit and, for an image, --terrain. Else the error of PARSER, before Earth
	Engine."""
	given = {k: getattr(args, k, None) for k in SOURCE_OPTIONS}
	given = {k: v for k, v in given.items() if v is not None and v != ''}
	image = 'image' in given
	ids = '--collection or --image' if hasattr(args, 'image') else '--collection'  # --image: only the command image
	if args.variable:
		if '/' in args.variable:  # an ID of Earth Engine given as a variable of the catalog (none has '/'), sensor or not
			parser.error(f'{args.variable} is not a variable of the catalog (monitoreo list): give an ID of Earth Engine '
			             f'with {ids} and --band, instead of VARIABLE (monitoreo asset ID says which)')
		if not args.sensor:
			parser.error(f'give the sensor of {args.variable} (--sensor; monitoreo list gives those of each variable)')
		if given:
			parser.error(f"{', '.join(SOURCE_OPTIONS[k] for k in given)}: only for the data of Earth Engine given by "
			             f'its ID ({ids} instead of VARIABLE and --sensor)')
		return {k: v for k, v in (('variable', args.variable), ('sensor', args.sensor),
		                          ('collection', args.collection)) if v}
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
		parser.error(f'give --band: the band of {asset} (one; monitoreo asset {asset} lists them)')
	if 'terrain' in given and not image:
		parser.error('--terrain is for --image (a fixed layer, e.g. a DEM), not for --collection')
	return dict(given, **({'collection': args.collection} if args.collection else {}))


def _table(rows, cols):
	widths = {c: max(len(c), *(len(str(r.get(c, ''))) for r in rows)) if rows else len(c) for c in cols}
	print('  '.join(c.ljust(widths[c]) for c in cols))
	for r in rows:
		print('  '.join(str(r.get(c, '')).ljust(widths[c]) for c in cols))


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
	p.add_argument('--theme', help='only those of a theme: vegetation, water, snow, fire, energy, atmosphere, climate '
	                               'or terrain (other data of Earth Engine: monitoreo asset and monitoreo community)')
	p.add_argument('--text')
	p.add_argument('--lang', default='en', choices=('en', 'es'))
	info = p = sub.add_parser('info', help='everything about a variable')
	p.add_argument('variable')
	p.add_argument('--sensor')
	p = sub.add_parser('parks', help='protected areas of WDPA by name')
	p.add_argument('text')
	p.add_argument('--limit', type=int, default=20)
	p.add_argument('--ramsar', action='store_true', help='only the Ramsar sites')
	p = sub.add_parser('units', help='administrative units of FAO GAUL 2025 by name')
	p.add_argument('text')
	p.add_argument('--level', type=int, default=1, choices=(1, 2),
	               help='1: regions, states...; 2: provinces, districts...')
	p.add_argument('--country', help='ISO3 code, e.g. ESP')
	p.add_argument('--limit', type=int, default=20)
	p = sub.add_parser('asset', help='what an image or collection of images of Earth Engine is: type, bands, units, '
	                                 'scale, dates and how to cite it (reads its metadata in Earth Engine)')
	p.add_argument('asset', metavar='ID', help="its ID, as in ee.ImageCollection('ID') (e.g. IDAHO_EPSCOR/TERRACLIMATE)")
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
	p.add_argument('--region', required=True, help='JSON dictionary, e.g. \'{"wdpa_id": 555513}\'')
	p.add_argument('--where', help=WHERE_HELP)
	p.add_argument('--start', required=True)
	p.add_argument('--end', required=True)
	p.add_argument('--step', default='monthly', choices=('daily', '16-day', 'monthly', 'annual'))
	p.add_argument('--metric', default='mean')
	p.add_argument('--stat', default='mean')
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
	p.add_argument('--start', help='first day (not for the fixed layers, ELEVATION and SLOPE of sensor Copernicus, '
	                               'nor for --image)')
	p.add_argument('--end', help='last day (not for the fixed layers)')
	p.add_argument('--metric', default='median')
	p.add_argument('--temporal', default='period', choices=('period', 'annual', 'monthly', '16-day'))
	p.add_argument('--interannual', default='mean')
	p.add_argument('--resolution', type=float, help='pixel size in metres (default: that of the data)')
	p.add_argument('--out', help='GeoTIFF file of the variable')
	p.add_argument('--rgb', metavar='FILE', help='GeoTIFF file of the true colour of the same images and pixels: bands '
	                                             'red, green and blue (surface reflectance), with the same metric; '
	                                             'with --out too, on its grid. Only the variables of Sentinel-2 and '
	                                             'Landsat and the cloud frequency of MODIS (rgb in monitoreo info), '
	                                             'with metric median, mean, min, max or pN')
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
		p.add_argument('--metric', default='mean')
		p.add_argument('--stat', default='mean')
		p.add_argument('--scale', type=float)
		p.add_argument('--csv')
		p.add_argument('--png')
	burn = p = sub.add_parser('burn', help='burn severity of a fire: dNBR with the classes of the USGS, the RBR, or the '
	                                       'RdNBR with the classes of Miller & Thode 2007')
	p.add_argument('--sensor', default='Sentinel-2', choices=('Sentinel-2', 'Landsat', 'Modis'),
	               help='Sentinel-2 (10 m, 20 m with --index RBR; since 2017), Landsat (30 m, since 1984) or Modis '
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
	                    'there) and without its offset (the dNBR of an unburned area outside the fire). Its classes '
	                    'were calibrated with Landsat TM (30 m) and field plots of 14 fires of the Sierra Nevada of '
	                    'California, mostly in conifer and live oak forests (also pinyon pine and sagebrush), with field '
	                    'data one year after the fire: give a period after about one year after the fire, in the '
	                    'season of the period before')
	p.add_argument('--collection', choices=BURN_COLLECTIONS, metavar='ID',
	               help='only with --index RdNBR and --sensor Modis: MODIS/061/MOD09GA (Terra, since 2000-02-24; '
	                    'default) or MODIS/061/MYD09GA (Aqua, since 2002-07-04)')
	p.add_argument('--metric', default='median', help='metric of the images of each period (default: median)')
	p.add_argument('--resolution', type=float, help='pixel size in metres (default: that of the data)')
	p.add_argument('--csv', help='CSV file of the hectares of each class (dNBR, RdNBR) or of the statistics (RBR)')
	p.add_argument('--out', help='GeoTIFF file, with the bands dnbr, severity, nbr_before and nbr_after (RBR: rbr, '
	                             'dnbr, nbr_before and nbr_after; RdNBR: rdnbr, severity, dnbr, nbr_before and '
	                             'nbr_after)')
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
	p.add_argument('--check', action='store_true', help='check the catalogue and every report of the site')
	p = sub.add_parser('serve', help='the viewer of results on this computer (with range requests, as the web servers)')
	p.add_argument('site', nargs='?', help='folder of the site (default: MONITOREO_SITE or ~/MonitorEO/visor)')
	p.add_argument('--port', type=int, default=8000)
	p = sub.add_parser('eecu', help='EECUs of Earth Engine spent this month: your research EECUs with the shared account '
	                                'of MonitorEO, or the monthly quota of your project')
	p.add_argument('--limit', help='monthly quota of your project: EECU-hours or tier (Community, Contributor, Partner; '
	                               'default: MONITOREO_EECU_LIMIT or Community, 150 EECU-hours)')
	p.add_argument('--lang', default='en', choices=('en', 'es'))
	p = sub.add_parser('about', help='what MonitorEO-OBSNEV is, who funds it and how to cite it')
	p.add_argument('--lang', default='en', choices=('en', 'es'))
	p = sub.add_parser('mcp', help='server MCP (stdio) for language models')
	p.add_argument('--no-update', action='store_true', help='do not install the last version of GitHub before starting')
	p = sub.add_parser('assistant', help='chat for managers, in a window of its own (language model of Ollama and '
	                                     'MCP server)')
	p.add_argument('--port', type=int, default=8765)
	p.add_argument('--browser', action='store_true', help='open it in the browser instead of in a window of its own')
	p.add_argument('--no-browser', action='store_true', help='open neither a window nor the browser (only the server)')
	p.add_argument('--no-update', action='store_true', help='do not install the last version of GitHub before starting')
	args = parser.parse_args(argv)
	if args.cmd in computes:  # what it computes, or its error before Earth Engine
		args.source = _source(args, computes[args.cmd])
	if args.cmd == 'info' and '/' in args.variable:  # an ID of Earth Engine: not the list of every variable
		info.error(f'{args.variable} is not a variable of the catalog (monitoreo list): monitoreo asset {args.variable} '
		           'describes an ID of Earth Engine')
	if args.cmd == 'image' and not (args.out or args.rgb):
		image.error('give --out (GeoTIFF of the variable), --rgb (GeoTIFF of its true colour) or both')
	if args.cmd == 'image' and args.rgb and not args.variable:
		image.error('--rgb is only for the variables of the catalog with a true colour (rgb in monitoreo info), not for '
		            'the data of Earth Engine given by its ID')
	if args.cmd == 'burn' and args.sensor == 'Modis' and args.index != 'RdNBR':
		burn.error(f'--sensor Modis is only for --index RdNBR: the {args.index} is computed with Sentinel-2 or Landsat')
	if args.cmd == 'burn' and args.collection and (args.index, args.sensor) != ('RdNBR', 'Modis'):
		burn.error('--collection is only for --index RdNBR with --sensor Modis: MODIS/061/MOD09GA (Terra, the default) '
		           'or MODIS/061/MYD09GA (Aqua)')

	if args.cmd == 'about':
		print(about.text(args.lang))
		return
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
	if args.cmd == 'community':  # the copy of its index in MonitorEO: without Earth Engine
		return _community(args, services)
	if args.cmd == 'landcover':  # the table of correspondences of catalog.json: without Earth Engine
		return _landcover(args, services)
	if args.cmd == 'mcp':
		_mcp(args)
		return
	if args.cmd == 'download':
		try:
			return _download(args, services)
		finally:
			_eecu_notice(services)
	if args.cmd == 'eecu':  # the research EECUs of the shared account, without connecting (also when they are spent)
		if args.project:
			services.init(args.project, warn=False)
		return _eecu(args, services)
	services.init(args.project, warn=False)
	try:
		_compute(args, services)
	finally:
		_eecu_notice(services)


def _eecu(args, services):
	try:
		u = services.eecu_usage(args.limit, refresh=True, lang=args.lang)
	except (ValueError, RuntimeError) as e:
		sys.exit(f'ERROR: {e}')
	print(f"{u['name']} {u['bar']}\n{u['text']}")
	if u['warning']:
		print(f"\nWARNING: {u['warning']}", file=sys.stderr)


def _eecu_notice(services):
	"""After a command that computes, warn when less than 10 % of the EECUs of the month are left."""
	warning = services.eecu_warning()
	if warning:
		print(f'\nWARNING: {warning}', file=sys.stderr)


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
	      'and how to cite it); then compute it with --collection or --image and --band')


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
		code = f'GAUL{args.level}_CODE'
		_table(_fmt(services.find_admin_units(args.text, args.level, args.country, args.limit)),
		       [code, 'DISP_EN', 'ISO3_CODE'])
		return
	if args.cmd in ('trend', 'compare'):
		_trend_or_compare(args, services)
		return
	if args.cmd == 'burn':
		_burn(args, services)
		return
	progress = lambda d, t: print(f'  {d}/{t} steps', file=sys.stderr)  # noqa: E731
	if args.cmd == 'image':
		_image(args, services)
		return
	try:
		res = services.time_series(json.loads(args.region), start=args.start, end=args.end, step=args.step,
		                           metric=args.metric, stat=args.stat, scale=args.scale, csv=args.csv, chart=args.png,
		                           progress=progress, where=_where(args), **args.source)
	except ValueError as e:  # e.g. an image given as a collection, a unit that is not UDUNITS
		sys.exit(_error(e, args))
	_table(_fmt(res['rows']), ['region', 'date', 'value', 'n_pixels', 'n_images'])
	print(f"\n{res['title']} | scale {res['scale']:g} m" + (f" | unit {res['unit']}" if res['unit'] else '')  # none given
	      + (f" | CSV {res['csv']}" if res['csv'] else '') + (f" | chart {res['chart']}" if res['chart'] else ''))


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
			res = services.download_image(region, resolution=resolution, path=args.out, progress=tiles, **same)
			images = 'fixed image' if res.get('images') is None else f"{res['images']} images"  # no dates: none
			print(f"{res['file']}: {res['name']} | {res['grid']['width']} x {res['grid']['height']} pixels of "
			      f"{res['resolution']:g} m | {images} | p5-p95 {res['min']:.4g} to {res['max']:.4g} "
			      f"{res['unit']}".rstrip() if res['min'] is not None else f"{res['file']}: no valid pixel")
			resolution = res['resolution']
		if args.rgb:
			res = services.download_rgb(region, resolution=resolution, path=args.rgb, progress=tiles, **same)
			print(f"{res['file']}: {res['name']} | {res['grid']['width']} x {res['grid']['height']} pixels of "
			      f"{res['resolution']:g} m | {res['images']} images | bands {', '.join(res['bands'])} | reflectance "
			      f"{res['min']:.4g} to {res['max']:.4g} (p2-p98)" if res['min'] is not None
			      else f"{res['file']}: no valid pixel")
	except ValueError as e:
		sys.exit(_error(e, args))


def _fmt(rows, digits=4):
	return [{k: (f'{v:.{digits}g}' if isinstance(v, float) else v) for k, v in r.items()} for r in rows]


def _trend_or_compare(args, services):
	progress = lambda d, t: print(f'  {d}/{t} steps', file=sys.stderr)  # noqa: E731
	try:
		region = json.loads(args.region)
		same = dict(args.source, start=args.start, end=args.end, step=args.step, metric=args.metric, stat=args.stat,
		            scale=args.scale, csv=args.csv, chart=args.png, progress=progress, where=_where(args))
		if args.cmd == 'trend':
			res = services.trend_table(region, **same)
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
	      + (f" | CSV {res['csv']}" if res['csv'] else '') + (f" | chart {res['chart']}" if res['chart'] else ''))


def _burn(args, services):
	"""Burn severity of a fire (services.burn_severity): the hectares of each class of the USGS and the burned area of
	each region (dNBR), the statistics of the RBR, or the hectares of each class of Miller & Thode 2007, the changed
	area of each region and the statistics of the RdNBR, and the CSV, GeoTIFF and README written."""
	from . import fire
	try:
		res = services.burn_severity(json.loads(args.region), args.sensor, args.start, args.end, args.other_start,
		                             args.other_end, args.metric, resolution=args.resolution, path=args.out,
		                             csv=args.csv, index=args.index, where=_where(args), collection=args.collection,
		                             progress=lambda d, t: print(f'  {d}/{t} tiles', file=sys.stderr))
	except ValueError as e:
		sys.exit(f'ERROR: {e}')

	def cells(rows):  # hectares with a decimal, the rest with 4 digits, and nothing for the open ends of the classes
		return [{k: '' if v is None else f'{v:.1f}' if k == 'ha' else f'{v:.4g}' if isinstance(v, float) else v
		         for k, v in r.items()} for r in rows]
	stats = ['region', 'mean', 'median', 'p10', 'p90', 'min', 'max', 'ha']
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
	print(f"\n{res['title']} | pixels of {res['scale']:g} m"
	      + (f" | CSV {res['csv']}" if res.get('csv') else '') + (f" | GeoTIFF {res['file']}" if res.get('file') else '')
	      + (f" | README {res['readme']}" if res.get('readme') else ''))


def _publish(args):
	from . import publish, services
	try:
		if not (args.reports or args.remove or args.check):
			publish.install_viewer(args.site)
			publish.update_catalog(args.site)
			print(f'Updated the viewer and the catalogue of {publish.site_folder(args.site)}')
		for rid in args.remove:
			res = services.remove_report(rid, args.site)
			print(f"Removed {rid} from {res['site']}")
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
		win = webview.create_window('MonitorEO Assistant', html=UPDATING, width=520, height=200, resizable=False)
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
