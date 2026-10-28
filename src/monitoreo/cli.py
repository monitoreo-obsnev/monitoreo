"""Command line of MonitorEO:

    monitoreo list [--sensor S] [--text T]           variables of the catalog
    monitoreo info VARIABLE [--sensor S]             everything about a variable
    monitoreo parks TEXT                             protected areas of WDPA with TEXT in their name
    monitoreo series VARIABLE --sensor S --region JSON --start D --end D [--step monthly] [--csv F] [--png F]
    monitoreo trend VARIABLE --sensor S --region JSON --start D --end D [--step annual|monthly|16-day] [--csv F]
                                                     seasonal trends (Mann-Kendall and Sen) of each part of the year
    monitoreo compare VARIABLE --sensor S --region JSON --start D --end D --other-start D --other-end D [--step]
                                                     a reference period against another, by part of the year
    monitoreo download RECIPE --area FILE|JSON --out FOLDER [--dry-run]   GeoTIFFs of a recipe of variables
    monitoreo publish REPORT.yaml [...] [--site S]   publish reports in the static viewer of results (administrators)
    monitoreo publish [--remove ID] [--check] [--site S]   remove a report, or check the site; with nothing else,
                                                     update its viewer (after updating monitoreo) and its catalogue
    monitoreo serve [SITE] [--port 8000]             the viewer of results on this computer
    monitoreo about [--lang es]                      what MonitorEO-OBSNEV is and who funds it
    monitoreo mcp [--no-update]                      server MCP (stdio) for language models, at the last version
                                                     of GitHub (installed when it starts, if needed)

The region is a JSON dictionary, e.g. '{"wdpa_id": 555513}' or '{"bbox": [-3.5, 37, -3, 37.2]}'. The Earth Engine
project is --project, the variable EE_PROJECT or (download) project: of the recipe. The recipe of download is a YAML
file with the variables, their metrics and the pixel sizes of the study area and of its ecoregions (see
monitoreo.recipe). The report of publish is a YAML file with its texts and the results of an analysis (see
monitoreo.publish); the site is --site, the variable MONITOREO_SITE or ~/MonitorEO/visor.
"""

import argparse
import json
import os
import subprocess
import sys

from . import __version__


def _table(rows, cols):
	widths = {c: max(len(c), *(len(str(r.get(c, ''))) for r in rows)) if rows else len(c) for c in cols}
	print('  '.join(c.ljust(widths[c]) for c in cols))
	for r in rows:
		print('  '.join(str(r.get(c, '')).ljust(widths[c]) for c in cols))


def main(argv=None):
	from . import about
	parser = argparse.ArgumentParser(prog='monitoreo', description=about.DESCRIPTION['en'],
	                                 epilog=about.ACKNOWLEDGEMENTS['en'])
	parser.add_argument('--version', action='version', version=__version__)
	parser.add_argument('--project', help='Earth Engine project (default: EE_PROJECT)')
	sub = parser.add_subparsers(dest='cmd', required=True)
	p = sub.add_parser('list', help='variables of the catalog')
	p.add_argument('--sensor')
	p.add_argument('--text')
	p.add_argument('--lang', default='es')
	p = sub.add_parser('info', help='everything about a variable')
	p.add_argument('variable')
	p.add_argument('--sensor')
	p = sub.add_parser('parks', help='protected areas of WDPA by name')
	p.add_argument('text')
	p.add_argument('--limit', type=int, default=20)
	p = sub.add_parser('series', help='time series of a variable over a region')
	p.add_argument('variable')
	p.add_argument('--sensor', required=True)
	p.add_argument('--region', required=True, help='JSON dictionary, e.g. \'{"wdpa_id": 555513}\'')
	p.add_argument('--start', required=True)
	p.add_argument('--end', required=True)
	p.add_argument('--step', default='monthly', choices=('daily', '16-day', 'monthly', 'annual'))
	p.add_argument('--metric', default='mean')
	p.add_argument('--stat', default='mean')
	p.add_argument('--scale', type=float)
	p.add_argument('--csv')
	p.add_argument('--png')
	for name, help_ in (('trend', 'seasonal trends (Mann-Kendall and Sen) of a variable over a region'),
	                    ('compare', 'a reference period against another, by part of the year')):
		p = sub.add_parser(name, help=help_)
		p.add_argument('variable')
		p.add_argument('--sensor', required=True)
		p.add_argument('--region', required=True, help='JSON dictionary, e.g. \'{"wdpa_id": 555513}\'')
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
	p = sub.add_parser('about', help='what MonitorEO-OBSNEV is and who funds it')
	p.add_argument('--lang', default='en', choices=('en', 'es'))
	p = sub.add_parser('mcp', help='server MCP (stdio) for language models')
	p.add_argument('--no-update', action='store_true', help='do not install the last version of GitHub before starting')
	args = parser.parse_args(argv)

	if args.cmd == 'about':
		print(about.text(args.lang))
		return
	if args.cmd == 'serve':
		from . import publish
		publish.serve(args.site, args.port)
		return
	if args.cmd == 'publish':
		return _publish(args)
	from . import services
	if args.cmd == 'list':
		_table(services.list_variables(args.sensor, args.text, args.lang),
		       ['ref', 'variable', 'sensor', 'collection', 'resolution_m', 'unit', 'name'])
		return
	if args.cmd == 'info':
		print(json.dumps(services.describe_variable(args.variable, args.sensor), ensure_ascii=False, indent=1))
		return
	if args.cmd == 'mcp':
		_mcp(args)
		return
	if args.cmd == 'download':
		return _download(args, services)
	services.init(args.project)
	if args.cmd == 'parks':
		_table(_fmt(services.find_protected_areas(args.text, args.limit)), ['SITE_ID', 'NAME', 'DESIG', 'ISO3', 'REP_AREA'])
		return
	if args.cmd in ('trend', 'compare'):
		_trend_or_compare(args, services)
		return
	res = services.time_series(json.loads(args.region), args.variable, args.sensor, args.start, args.end, args.step,
	                           args.metric, args.stat, scale=args.scale, csv=args.csv, chart=args.png,
	                           progress=lambda d, t: print(f'  {d}/{t} steps', file=sys.stderr))
	_table(_fmt(res['rows']), ['region', 'date', 'value', 'n_pixels', 'n_images'])
	print(f"\n{res['title']} | scale {res['scale']:g} m | unit {res['unit']}"
	      + (f" | CSV {res['csv']}" if res['csv'] else '') + (f" | chart {res['chart']}" if res['chart'] else ''))


def _fmt(rows, digits=4):
	return [{k: (f'{v:.{digits}g}' if isinstance(v, float) else v) for k, v in r.items()} for r in rows]


def _trend_or_compare(args, services):
	progress = lambda d, t: print(f'  {d}/{t} steps', file=sys.stderr)  # noqa: E731
	region = json.loads(args.region)
	if args.cmd == 'trend':
		res = services.trend_table(region, args.variable, args.sensor, args.start, args.end, args.step, args.metric,
		                           args.stat, scale=args.scale, csv=args.csv, chart=args.png, progress=progress)
		_table(_fmt(res['rows']), ['region', 'key', 'label', 'n', 'tau', 'z', 'p_value', 'significant', 'slope',
		                           'intercept'])
		extra = f" | slope in {res['unit']} / year"
	else:
		res = services.compare_series(region, args.variable, args.sensor, args.start, args.end, args.other_start,
		                              args.other_end, args.step, args.metric, args.stat, scale=args.scale, csv=args.csv,
		                              chart=args.png, progress=progress)
		_table(_fmt(res['profile']), ['region', 'key', 'label', 'reference', 'other', 'difference', 'n_reference',
		                              'n_other'])
		extra = ''
	print(f"\n{res['title']} | scale {res['scale']:g} m{extra}"
	      + (f" | CSV {res['csv']}" if res['csv'] else '') + (f" | chart {res['chart']}" if res['chart'] else ''))


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


def _download(args, services):
	from . import recipe
	try:
		rec = recipe.read(args.recipe)
		services.init(args.project or rec.get('project') or None)
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
