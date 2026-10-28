"""Command line of MonitorEO:

    monitoreo list [--sensor S] [--text T]           variables of the catalog
    monitoreo info VARIABLE [--sensor S]             everything about a variable
    monitoreo parks TEXT                             protected areas of WDPA with TEXT in their name
    monitoreo series VARIABLE --sensor S --region JSON --start D --end D [--step monthly] [--csv F] [--png F]
    monitoreo mcp                                    server MCP (stdio) for language models

The region is a JSON dictionary, e.g. '{"wdpa_id": 555513}' or '{"bbox": [-3.5, 37, -3, 37.2]}'. The Earth Engine
project is --project or the variable EE_PROJECT.
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


if __name__ == '__main__':
	main()
