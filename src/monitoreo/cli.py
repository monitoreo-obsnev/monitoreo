"""Command line of MonitorEO:

    monitoreo list [--sensor S] [--text T]           variables of the catalog
    monitoreo info VARIABLE [--sensor S]             everything about a variable
    monitoreo parks TEXT                             protected areas of WDPA with TEXT in their name
    monitoreo series VARIABLE --sensor S --region JSON --start D --end D [--step monthly] [--csv F] [--png F]
    monitoreo download RECIPE --area FILE|JSON --out FOLDER [--dry-run]   GeoTIFFs of a recipe of variables
    monitoreo mcp                                    server MCP (stdio) for language models

The region is a JSON dictionary, e.g. '{"wdpa_id": 555513}' or '{"bbox": [-3.5, 37, -3, 37.2]}'. The Earth Engine
project is --project, the variable EE_PROJECT or (download) project: of the recipe. The recipe of download is a YAML
file with the variables, their metrics and the pixel sizes of the study area and of its ecoregions (see
monitoreo.recipe).
"""

import argparse
import json
import sys

from . import __version__


def _table(rows, cols):
	widths = {c: max(len(c), *(len(str(r.get(c, ''))) for r in rows)) if rows else len(c) for c in cols}
	print('  '.join(c.ljust(widths[c]) for c in cols))
	for r in rows:
		print('  '.join(str(r.get(c, '')).ljust(widths[c]) for c in cols))


def main(argv=None):
	parser = argparse.ArgumentParser(prog='monitoreo', description='MonitorEO (OBSNEV) with Google Earth Engine.')
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
	sub.add_parser('mcp', help='server MCP (stdio) for language models')
	args = parser.parse_args(argv)

	from . import services
	if args.cmd == 'list':
		_table(services.list_variables(args.sensor, args.text, args.lang),
		       ['ref', 'variable', 'sensor', 'collection', 'resolution_m', 'unit', 'name'])
		return
	if args.cmd == 'info':
		print(json.dumps(services.describe_variable(args.variable, args.sensor), ensure_ascii=False, indent=1))
		return
	if args.cmd == 'mcp':
		from . import mcp_server
		mcp_server.main()
		return
	if args.cmd == 'download':
		return _download(args, services)
	services.init(args.project)
	if args.cmd == 'parks':
		_table(services.find_protected_areas(args.text, args.limit), ['SITE_ID', 'NAME', 'DESIG', 'ISO3', 'REP_AREA'])
		return
	res = services.time_series(json.loads(args.region), args.variable, args.sensor, args.start, args.end, args.step,
	                           args.metric, args.stat, scale=args.scale, csv=args.csv, chart=args.png,
	                           progress=lambda d, t: print(f'  {d}/{t} steps', file=sys.stderr))
	_table(res['rows'], ['region', 'date', 'value', 'n_pixels', 'n_images'])
	print(f"\n{res['title']} | scale {res['scale']:g} m | unit {res['unit']}"
	      + (f" | CSV {res['csv']}" if res['csv'] else '') + (f" | chart {res['chart']}" if res['chart'] else ''))


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
