"""Printable report of results of MonitorEO in a single HTML file, to open with the browser and print to PDF.

    report.write(items, title='...', question='...', project='...')   -> path of the HTML file

ITEMS are the results of the tools, in the order of the report: {'tool', 'args', 'result'} with the arguments of the
call and its answer (the dictionary of the MCP server or of monitoreo.services), and optionally 'image' (a PNG file
or its data as a data: URL) when the answer does not name its chart or preview, and 'table': False to leave out its
table of values. Everything in the report comes from
them and from the catalog: it has no text written by a language model, nor an interpretation of the results. The
charts, maps and logos are embedded in the file, so it can be moved, sent and opened without connection; long tables
go to an annex at the end. It ends with the references of the results (monitoreo.references: those of their variables,
data and methods, of Google Earth Engine and of MonitorEO), numbered, each result with the numbers of its own, and the
credits that the terms of use of the data ask for. The texts are in English, as those of the viewer of results
(monitoreo.publish).
"""

import base64
import datetime as dt
import html
import math
import os
import re
import urllib.request

from . import __version__, catalog, fire, references, services
from .publish import MONTHS, PARTS, SENSORS, STEPS, _colours, default_title, fire_variable, is_static, period_text, \
	python_call, season_text, slug, unit_text

FOLDER = os.path.join(os.path.expanduser(os.environ.get('MONITOREO_OUTPUT') or '~/MonitorEO'), 'informes')
MAX_ROWS = 40  # longer tables go to the annex

TITLES = {'region_stats': 'Statistics of {var}, {period}{season}', 'map_layer': 'Map of {var}, {period}{season}',
          'trend_map': 'Map of the trend of {var}, {period}{season}',
          'compare_map': 'Map of the difference of {var}: {other} minus {period}{season}'}

METHODS = {
	'time_series': 'For each time step, the temporal metric of the images of the step on each pixel and, over the '
	               'region, the spatial statistic of those values.',
	'region_stats': 'The temporal metric of the images of the period on each pixel and its statistics over the region.',
	'map_layer': 'The temporal metric of the images of the period on each pixel.',
	'trend_table': 'For each part of the year, its value in each year (the spatial statistic of the temporal metric) '
	               "and the trend of those values over the years: Mann-Kendall test (τ, Z and p-value) and Sen's "
	               'slope (change per year).',
	'trend_map': "The trend computed on each pixel: Mann-Kendall test and Sen's slope (change per year).",
	'compare_series': 'For each part of the year, the mean of its values in the years of each period and the '
	                  'difference between both (other period minus reference period).',
	'compare_map': 'On each pixel, the temporal metric of the other period minus that of the reference period.',
	'download_image': 'The temporal metric of the images of the period on each pixel, in a GeoTIFF (float32, NoData '
	                  '-9999).',
	'download_trend': "The trend computed on each pixel (Mann-Kendall test and Sen's slope, change per year), in a "
	                  'GeoTIFF with a band per result (NoData -9999).',
	'download_comparison': 'On each pixel, the temporal metric of the other period minus that of the reference '
	                       'period, in a GeoTIFF with the bands difference, reference and other (NoData -9999).',
	'download_variables': 'Each variable of the recipe, with its metrics, in a GeoTIFF per variable on aligned grids '
	                      'of the study area and, if the recipe asks for it, of its ecoregions.',
	'burn_severity': 'dNBR: NBR of the period before the fire minus NBR of the period after it, with the severity '
	                 'classes of the USGS (Key and Benson, 2006). Burned area: dNBR ≥ 0.1.',
	'static': 'A fixed layer, without dates: its value on each pixel (no period, temporal metric or pixel filters).',
	'burn_severity_rbr': 'RBR (Relativized Burn Ratio, Parks et al., 2014): dNBR / (NBR before + 1.001), with the NBR '
	                     'of the bands B8A and B12 of Sentinel-2 (NIR and SWIR2 of Landsat), as Silva-Cardoza et al. '
	                     '(2022), without phenological correction and without the factor 1000 of the articles. A '
	                     'continuous index, without classes.',
}

FILTERS = {'clouds': 'clouds', 'water': 'water', 'snow': 'snow', 'aerosols': 'aerosols'}
STATS = {'mean': 'mean', 'median': 'median', 'min': 'minimum', 'max': 'maximum', 'std': 'standard deviation',
         'sum': 'sum', 'count': 'count'}

# the table of each tool: its key in the answer (the first one found), and its columns (key, label); in the labels,
# {u} is the unit of the variable and {uy} that unit per year
TABLES = {
	'time_series': (('rows',), [('region', 'Region'), ('date', 'Date'), ('value', 'Value{u}'),
	                            ('n_images', 'Images'), ('n_pixels', 'Valid pixels')]),
	'trend_table': (('trends', 'rows'), [('region', 'Region'), ('label', 'Part of the year'), ('n', 'Years'),
	                                     ('slope', "Sen's slope{uy}"), ('tau', "Kendall's τ"),
	                                     ('p_value', 'p-value'), ('significant', 'Significant')]),
	'compare_series': (('comparison', 'profile'), [('region', 'Region'), ('label', 'Part of the year'),
	                                               ('reference', 'Reference period{u}'), ('other', 'Other period{u}'),
	                                               ('difference', 'Difference{u}'), ('n_reference', 'Years (reference)'),
	                                               ('n_other', 'Years (other)')]),
	'region_stats': (('rows',), [('region', 'Region'), ('mean', 'Mean{u}'), ('std', 'Std. dev.'), ('min', 'Min.'),
	                           ('p5', 'P5'), ('p50', 'Median'), ('p95', 'P95'), ('max', 'Max.'),
	                           ('n_pixels', 'Pixels')]),
	'download_variables': (('files',), [('file', 'File'), ('images', 'Images'), ('pixel_filters', 'Discarded pixels')]),
	'burn_severity': (('classes', 'stats'), [('region', 'Region'), ('label', 'Severity class'), ('dnbr_min', 'dNBR from'),
	                                          ('dnbr_max', 'dNBR to'), ('mean', 'RBR mean'), ('median', 'RBR median'),
	                                          ('p10', 'RBR percentile 10'), ('p90', 'RBR percentile 90'),
	                                          ('min', 'RBR minimum'), ('max', 'RBR maximum'), ('ha', 'Hectares')]),
}

CSS = """
:root { --ink: #1d2327; --muted: #5b6770; --line: #d5dbe0; --accent: #2f6b3f; --soft: #f3f6f4; }
* { box-sizing: border-box; }
body { margin: 0; background: #fff; color: var(--ink); font: 15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto,
       sans-serif; }
main { max-width: 860px; margin: 0 auto; padding: 24px 16px 48px; }
header.top { display: flex; align-items: center; gap: 16px; border-bottom: 2px solid var(--accent);
             padding-bottom: 12px; }
header.top img { height: 56px; }
h1 { font-size: 1.6em; line-height: 1.25; margin: 18px 0 6px; }
h2 { font-size: 1.2em; margin: 0 0 8px; color: var(--accent); break-after: avoid; }
h3 { font-size: 1em; margin: 14px 0 6px; break-after: avoid; }
.meta, .note, figcaption { color: var(--muted); font-size: .9em; }
.question { background: var(--soft); border-left: 4px solid var(--accent); padding: 8px 12px; margin: 12px 0; }
section.result { border-top: 1px solid var(--line); padding-top: 18px; margin-top: 22px; }
dl { display: grid; grid-template-columns: max-content 1fr; gap: 2px 14px; margin: 8px 0; font-size: .92em; }
dt { color: var(--muted); }
dd { margin: 0; }
figure { margin: 12px 0; break-inside: avoid; }
figure img { max-width: 100%; border: 1px solid var(--line); }
table { border-collapse: collapse; width: 100%; font-size: .85em; margin: 8px 0; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th, td { border-bottom: 1px solid var(--line); padding: 3px 6px; text-align: right; }
th { background: var(--soft); }
th:first-child, td:first-child, td.text { text-align: left; }
.legend { display: flex; align-items: center; gap: 8px; font-size: .85em; }
.legend .bar { height: 12px; width: 220px; border: 1px solid var(--line); }
.legend.classes { flex-wrap: wrap; gap: 4px 14px; }
.legend .class { display: inline-flex; align-items: center; gap: 5px; }
.legend .swatch { width: 14px; height: 14px; border: 1px solid var(--line); flex: none;
                  -webkit-print-color-adjust: exact; print-color-adjust: exact; }
code { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .8em; word-break: break-all;
       display: block; background: var(--soft); padding: 6px 8px; }
footer { border-top: 2px solid var(--accent); margin-top: 32px; padding-top: 12px; font-size: .85em; }
footer .logos { display: flex; flex-wrap: wrap; gap: 18px; align-items: center; margin-top: 10px; }
footer .logos img { height: 44px; }
ol.references { padding-left: 2.2em; font-size: .88em; }
ol.references li { margin: 3px 0; break-inside: avoid; }
a { color: var(--accent); word-break: break-word; }
.print { position: fixed; right: 16px; bottom: 16px; background: var(--accent); color: #fff; border: 0;
         border-radius: 6px; padding: 10px 14px; font: inherit; cursor: pointer; }
.hint { font-size: .85em; color: var(--muted); background: var(--soft); padding: 8px 12px; border-radius: 6px; }
@page { size: A4; margin: 16mm 14mm 18mm; }
@media print {
  body { font-size: 10pt; }
  main { max-width: none; padding: 0; }
  .noprint { display: none !important; }
  section.result { break-before: auto; }
  .annex { break-before: page; }
}
"""


def write(items, path=None, title=None, question=None, project=None, names=None, date=None, shared=False):
	"""Write the report of ITEMS (see the module) to PATH (default: a file in ~/MonitorEO/informes named after the
	title and the time). QUESTION is that of the user, PROJECT the Google Cloud project that computed the results (or
	SHARED: the shared account of MonitorEO) and NAMES the names of the protected areas by their WDPA ID. Returns the
	path."""
	title = title or 'MonitorEO report'
	if not path:
		os.makedirs(FOLDER, exist_ok=True)
		path = os.path.join(FOLDER, f'{slug(title)[:60] or "report"}_{dt.datetime.now():%Y%m%d-%H%M%S}.html')
	text = html_report(items, title, question, project, names, date, shared)
	with open(path, 'w', encoding='utf-8') as f:
		f.write(text)
	return path


def html_report(items, title, question=None, project=None, names=None, date=None, shared=False):
	"""The HTML of the report (see write)."""
	date = date or dt.date.today()
	a = services.about('en')
	logos = [_data_url(p) for p in a['logos']]
	annex = []
	refs, credits, numbers = references.of_items(items, date)
	sections = [_item(item, i + 1, names or {}, annex, numbers[i]) for i, item in enumerate(items)]
	out = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
	       '<meta name="viewport" content="width=device-width, initial-scale=1">',
	       f'<title>{_e(title)}</title><style>{CSS}</style></head><body><main>',
	       f'<header class="top"><img src="{logos[0]}" alt="MonitorEO-OBSNEV"><div><b>MonitorEO-OBSNEV</b><br>'
	       '<span class="meta">Sierra Nevada Global Change Observatory · University of Granada</span></div>'
	       '</header>',
	       '<p class="hint noprint">To save it as a PDF, with no printer: <b>Print or save as PDF</b> and, as the '
	       'destination, <b>Save as PDF</b> (<b>Save to PDF</b> in Firefox; in Safari, the menu <b>PDF</b> at the bottom '
	       'of the dialog). Turn off '
	       '“Headers and footers” in the options of the print dialog.</p>',
	       f'<h1>{_e(title)}</h1>',
	       f'<p class="meta">{_long_date(date)} · {len(items)} result{"s" if len(items) != 1 else ""}'
	       + (f' · computed in Google Earth Engine with the project {_e(project)}' if project else
	          ' · computed in Google Earth Engine with the shared account of MonitorEO' if shared else '') + '</p>']
	if question:
		out.append(f'<div class="question"><b>Question:</b> {_e(question)}</div>')
	out.append('<p class="note">This report gathers the results of the computations and how they were obtained, '
	           'without interpreting them. Their interpretation is up to technical staff.</p>')
	out += sections
	if refs:
		out.append('<section class="result"><h2>References</h2><ol class="references">' + ''.join(
			f'<li>{_e(r["citation"])}' + (f' <a href="{_e(r["url"])}">{_e(r["url"])}</a>' if r.get('url') else '')
			+ '</li>' for r in refs) + '</ol>'
			+ (f'<p class="note">{"<br>".join(_e(c) for c in credits)}</p>' if credits else '') + '</section>')
	if annex:
		out.append('<section class="annex"><h2>Annex: full tables</h2>' + ''.join(annex) + '</section>')
	out.append(f'<footer><p><b>How to cite MonitorEO:</b> {_e(a["citation"])}</p>'
	           f'<p>{_e(a["acknowledgements"])}</p>'
	           f'<p class="meta">Made with MonitorEO {_e(__version__)} · Manual: {_e(a["manual"])}</p>'
	           '<div class="logos">' + ''.join(f'<img src="{u}" alt="">' for u in logos) + '</div></footer>')
	out.append('<button class="print noprint" onclick="window.print()">Print or save as PDF</button>')
	out.append('</main></body></html>')
	return '\n'.join(out)


def item_references(tool, args, result=None, date=None):
	"""What to cite with a result: {'references', 'credits'} (see monitoreo.references.of_result)."""
	return references.of_result(tool, args, result, date)


def item_title(tool, args, result=None):
	"""The title in English of the result of a call."""
	if tool in TITLES:
		v = f"{args.get('variable', '')} ({SENSORS.get(args.get('sensor'), args.get('sensor') or '')})"
		if tool in ('region_stats', 'map_layer') and (is_static(args) or not (args.get('start') and args.get('end'))):
			return TITLES[tool].split(',')[0].format(var=v)  # elevation, slope: no period
		other = period_text(args['other_start'], args['other_end']) if args.get('other_start') else ''
		return TITLES[tool].format(var=v, period=period_text(args['start'], args['end']), other=other,
		                           season=season_text(args.get('season')))
	if tool in ('time_series', 'trend_table', 'compare_series', 'burn_severity', 'download_image', 'download_trend',
	            'download_comparison'):
		return default_title(tool, args) + (' (GeoTIFF)' if tool == 'download_image' else '')
	if tool == 'download_variables':
		return f"Variables in GeoTIFF: {args.get('name', '')}" + (' (plan, not downloaded)' if args.get('dry_run') else '')
	return (result or {}).get('title') or tool


def item_facts(tool, args, result=None, names=None):
	"""How a result was computed: [(label, text)] in English."""
	result = result if isinstance(result, dict) else {}
	if tool == 'download_variables':
		return _recipe_facts(args, result, names)
	facts = [('Region', region_text(args.get('region'), names or {}))]
	if args.get('where'):
		facts.append(('Pixels of the region', 'only where ' + where_text(args['where'])))
	entry = _entry(args.get('variable') or (fire_variable(args) if tool == 'burn_severity' else None), args.get('sensor') or
	               ('Sentinel-2' if tool == 'burn_severity' else None))
	if entry:
		facts.append(('Variable', f"{entry.get('name', '')} ({entry.get('index', '')})"))
		facts.append(('Sensor', f"{SENSORS.get(entry['sensor'], entry['sensor'])}, pixel of {entry.get('m', '?')} m, "
		                        f"collection {entry.get('col', '')}"))
	static = bool(entry and entry.get('static'))  # elevation, slope: no period, temporal metric or pixel filters
	if args.get('start') and args.get('end') and not static:
		label = 'Before the fire' if tool == 'burn_severity' else \
			'Reference period' if args.get('other_start') else 'Period'
		facts.append((label, period_text(args['start'], args['end']) + season_text(args.get('season'))))
	if args.get('other_start') and args.get('other_end'):
		label = 'After the fire' if tool == 'burn_severity' else 'Other period'
		facts.append((label, period_text(args['other_start'], args['other_end']) + season_text(args.get('season'))))
	if tool in ('time_series', 'trend_table', 'compare_series', 'trend_map', 'download_trend'):
		step = args.get('step') or ('annual' if 'trend' in tool else 'monthly')
		facts.append(('Step', STEPS.get(step, step)))
	if tool in ('trend_map', 'download_trend') and args.get('part'):
		part = int(args['part'])
		facts.append(('Part of the year', MONTHS[part - 1] if args.get('step') == 'monthly' else f'16-day period {part}'))
	metric = args.get('metric') or ('median' if tool in ('region_stats', 'map_layer', 'compare_map', 'burn_severity',
	                                                      'download_image', 'download_comparison') else 'mean')
	if not static:
		facts.append(('Temporal metric', _stat(metric)))
	if args.get('temporal') in PARTS and not static:  # the metric of each year, month or 16 days, then between years
		each = {'annual': 'year', 'monthly': 'month', '16-day': '16-day period'}[args['temporal']]
		facts.append(('Temporal aggregation', f"{_stat(metric)} of each {each} and, between the years, "
		                                       f"{_stat(args.get('interannual') or 'mean')} (interannual value)"))
	if tool in ('time_series', 'trend_table', 'compare_series'):
		facts.append(('Spatial statistic', _stat(args.get('stat') or 'mean')))
	if entry and not static:
		filters = dict(entry.get('pixel_filters') or {})
		if entry.get('fixed_filters') is None:  # the SCF: always clouds and water, whatever the quality
			filters.update({k: bool(v) for k, v in (args.get('quality') or {}).items() if k in FILTERS})
		on = [FILTERS[k] for k, v in filters.items() if v and k in FILTERS]
		facts.append(('Discarded pixels', ', '.join(on) if on else 'none'))
	if result.get('scale'):
		facts.append(('Pixel size of the computation', f"{_num(result['scale'])} m"))
	if tool == 'trend_table':
		facts.append(('Significant if', f"p < {_num(args.get('alpha') or 0.05)}"))
	if tool in ('trend_map', 'download_trend') and args.get('alpha'):
		facts.append(('Pixels', f"only those with a significant trend (Mann-Kendall, p < {_num(args['alpha'])})"))
	if tool == 'burn_severity' and result.get('burned_ha'):
		burned = result['burned_ha']
		facts.append(('Burned area', '; '.join(f'{k}: {_num(v)} ha' for k, v in burned.items()) if len(burned) > 1
		              else f'{_num(next(iter(burned.values())))} ha'))
	grid = result.get('grid')
	if isinstance(grid, dict) and grid.get('width'):
		native = result.get('native_resolution')
		res = result.get('resolution') or grid.get('resolution')
		facts.append(('GeoTIFF', f"{_num(grid['width'])} × {_num(grid['height'])} pixels of {_num(res)} m"
		                         + (f' (the data, of {_num(native)} m)' if native and native != res else '')
		                         + f", in {grid.get('crs', '')}"))
	if result.get('bands'):
		facts.append(('Bands', ', '.join(map(str, result['bands']))))
	if result.get('images'):
		facts.append(('Images', _num(result['images'])))
	if tool == 'download_image' and result.get('min') is not None:
		unit = unit_text(result.get('unit'))
		facts.append(('Values (percentiles 5 and 95)', f"{_num(result['min'])} to {_num(result['max'])}"
		                                               + (f' {unit}' if unit else '')))
	if tool in METHODS:
		rbr = tool == 'burn_severity' and fire_variable(args) == 'RBR'
		facts.append(('Method', METHODS['static'] if static else METHODS['burn_severity_rbr' if rbr else tool]))
	return facts


def _recipe_facts(args, result, names):
	"""How the variables of a recipe (download_variables) were downloaded."""
	recipe = args.get('recipe') or {}
	facts = [('Study area', region_text(args.get('area'), names or {}))]
	variables = []
	for v in recipe.get('variables') or []:
		metric = v.get('metric') or 'median'
		metrics = ', '.join(_stat(m) for m in (metric if isinstance(metric, list) else [metric]))
		what = v.get('index') or v.get('name') or v.get('image') or '?'
		variables.append(f"{what}{' (' + v['sensor'] + ')' if v.get('sensor') else ''}: {metrics}")
	if variables:
		facts.append(('Variables', '; '.join(variables)))
	period = recipe.get('period')
	if isinstance(period, list) and len(period) == 2:
		facts.append(('Period', period_text(*period) + season_text(recipe.get('season'))))
	for name, g in (result.get('grids') or {}).items():
		label = {'study': 'Grid of the study area', 'ecoregion': 'Grid of the ecoregions'}.get(name, name)
		facts.append((label, f"{_num(g.get('width'))} × {_num(g.get('height'))} pixels of {_num(g.get('resolution'))} m"
		                     f", {_num(g.get('mb_per_variable'))} MB per variable"))
	if args.get('dry_run'):
		facts.append(('Download', 'only the plan: nothing has been downloaded'))
	elif result:
		facts.append(('Download', 'complete' if result.get('done') else
		              f"pending: {len(result.get('pending') or [])} exports to Google Drive running"))
		if result.get('folders'):
			facts.append(('Folders', '; '.join(map(str, result['folders'].values() if isinstance(result['folders'], dict)
			                                        else result['folders']))))
	facts.append(('Method', METHODS['download_variables']))
	return facts


def item_table(tool, result, args=None):
	"""The table of a result: (columns, rows) with the values already formatted, or None."""
	if tool not in TABLES:
		return None
	keys, cols = TABLES[tool]
	rows = result if isinstance(result, list) else next((result.get(k) for k in keys if isinstance(result, dict) and
	                                                     result.get(k)), None)
	if not isinstance(rows, list) or not rows:
		return None
	unit = unit_text(result.get('unit') if isinstance(result, dict) else (_entry(
		(args or {}).get('variable'), (args or {}).get('sensor')) or {}).get('unit'))
	u, uy = (f' ({unit})' if unit else ''), f" ({unit_text(unit, per_year=True)})"
	if len({str(r.get('region')) for r in rows}) <= 1:
		cols = [c for c in cols if c[0] != 'region']
	cols = [c for c in cols if any(c[0] in r for r in rows)]
	labels = [label.format(u=u, uy=uy) for _, label in cols]
	body = [[r.get(k) if k in ('region', 'label', 'date', 'file') else
	         ', '.join(FILTERS.get(x, x) for x in r[k]) if isinstance(r.get(k), list) else _num(r.get(k))
	         for k, _ in cols] for r in rows]
	return labels, body


def where_text(where):
	"""The conditions WHERE of the pixels of a study area in English, e.g. «ELEVATION (Copernicus) ≥ 1500 m and PRECIP
	(TerraClimate, sum of each year, mean between the years) ≤ 600 mm/month»."""
	parts = []
	for c in [where] if isinstance(where, dict) else where or []:
		if not isinstance(c, dict):
			continue
		e = _entry(c.get('variable'), c.get('sensor')) or {}
		unit = unit_text(catalog.unit_of(e.get('unit'), c.get('metric') or e.get('metric') or 'mean'))
		how = [SENSORS.get(e.get('sensor'), e.get('sensor') or c.get('sensor') or '')]
		if not e.get('static'):
			temporal = c.get('temporal') or 'period'
			metric = _stat(c.get('metric') or e.get('metric') or 'mean')
			if temporal in PARTS:
				each = {'annual': 'year', 'monthly': 'month', '16-day': '16-day period'}[temporal]
				how.append(f"{metric} of each {each}, {_stat(c.get('interannual') or 'mean')} between the years")
			else:
				how.append(f'{metric} of the period')
			if c.get('period'):
				how.append(f"{c['period'][0]} / {c['period'][1]}")
		name = f"{c.get('variable')} ({', '.join(h for h in how if h)})"
		limits = [f"≥ {_num(c['min'])}" if c.get('min') is not None else '',
		          f"≤ {_num(c['max'])}" if c.get('max') is not None else '']
		parts.append(f"{name} {' and '.join(x for x in limits if x)}" + (f' {unit}' if unit else ''))
	return '; '.join(parts)


def region_text(region, names=None):
	"""A region of the tools (see monitoreo.areas) in English."""
	names = names or {}
	if not isinstance(region, dict):
		return str(region)
	if 'wdpa_id' in region:
		ids = region['wdpa_id'] if isinstance(region['wdpa_id'], list) else [region['wdpa_id']]
		return '; '.join(f'{names[str(i)]} (WDPA {i})' if str(i) in names else f'Protected area WDPA {i}'
		                 for i in ids)
	if 'wdpa_name' in region:
		return f"Protected area “{region['wdpa_name']}”"
	if 'ecoregion_id' in region:
		return f"Ecoregion {region['ecoregion_id']}"
	if 'ecoregion_at' in region:
		lon, lat = region['ecoregion_at']
		return f'Ecoregion of the point {_num(lat)}, {_num(lon)} (lat., lon.)'
	if 'country' in region:
		codes = region['country'] if isinstance(region['country'], list) else [region['country']]
		return '; '.join(f"{names.get(f'country:{str(c).upper()}', str(c).upper())} (country, FAO GAUL 2025)"
		                 for c in codes)
	for level in (1, 2):
		if f'admin{level}' in region:
			codes = region[f'admin{level}'] if isinstance(region[f'admin{level}'], list) else [region[f'admin{level}']]
			return '; '.join(f"{names[f'admin{level}:{c}']} (administrative unit, FAO GAUL 2025)"
			                 if f'admin{level}:{c}' in names else
			                 f'Administrative unit {c} of level {level} (FAO GAUL 2025)' for c in codes)
	if 'island_at' in region:
		lon, lat = region['island_at']
		return f'Island at the point {_num(lat)}, {_num(lon)} (lat., lon.)'
	if 'bbox' in region:
		w, s, e, n = region['bbox']
		return f'Rectangle of longitude {_num(w)} to {_num(e)} and latitude {_num(s)} to {_num(n)}'
	if 'point' in region:
		lon, lat = region['point']
		where = f"{lat:.5f}, {lon:.5f}"
		if not region.get('buffer'):
			return f'Pixel at {where} (lat., lon.)'
		return f"Circle of {_num(region['buffer'])} m radius at {where} (lat., lon.)"
	if 'file' in region:
		return names.get(str(region['file'])) or f"File {os.path.basename(str(region['file']))}"
	if 'geojson' in region:
		g = region['geojson']
		n = len(g.get('features', [])) if isinstance(g, dict) and g.get('type') == 'FeatureCollection' else 1
		return f'GeoJSON geometry ({n} feature{"s" if n != 1 else ""})'
	return str(region)


def _item(item, n, names, annex, refs=()):
	tool, args, result = item['tool'], item.get('args') or {}, item.get('result')
	title = item.get('title') or item_title(tool, args, result if isinstance(result, dict) else None)
	out = [f'<section class="result"><h2>{n}. {_e(title)}</h2><dl>']
	facts = item_facts(tool, args, result, names) + view_facts(item)
	if refs:
		facts.append(('References', ', '.join(f'[{i}]' for i in refs) + ' (at the end)'))
	out += [f'<dt>{_e(k)}</dt><dd>{_e(v)}</dd>' for k, v in facts]
	out.append('</dl>')
	image = item.get('image') or (result.get('chart') or result.get('thumbnail') if isinstance(result, dict) else None)
	if image:
		src = image if str(image).startswith('data:') else _data_url(image) if os.path.exists(image) else None
		if src:
			out.append(f'<figure><img src="{src}" alt="{_e(title)}">')
			style = map_style(tool, args, result)
			if style:
				out.append(_class_legend(style['classes']) if style.get('classes') else _legend({**result, **style}))
			out.append('</figure>')
	table = item_table(tool, result, args) if item.get('table', True) else None
	if table:
		labels, rows = table
		if len(rows) <= MAX_ROWS:
			out.append(_table(labels, rows))
		else:
			out.append(f'<p class="note">Table of {len(rows)} rows: in the annex (table {n}).</p>')
			annex.append(f'<h3>Table {n}. {_e(title)}</h3>' + _table(labels, rows))
	files = [result.get(k) for k in ('csv', 'file') if isinstance(result, dict) and result.get(k)]
	if files:
		out.append('<p class="note">Files: ' + ' · '.join(_e(f) for f in files) + '</p>')
	call = python_call(tool, args)
	if call:
		out.append(f'<h3>To reproduce it in Python</h3><code>import monitoreo.services as mo<br>{_e(call)}</code>')
	out.append('</section>')
	return ''.join(out)


# the base maps of the interactive map of the assistant, to draw its views (map_view): tiles {z}/{x}/{y}, or WMS
BASEMAPS = {
	'osm': {'name': 'OpenStreetMap', 'tiles': 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', 'max': 19,
	        'credit': '© OpenStreetMap contributors'},
	'eox': {'name': 'Sentinel-2 cloudless 2023 by EOX (s2maps.eu, modified Copernicus Sentinel data)', 'max': 15,
	        'tiles': 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/default/g/{z}/{y}/{x}.jpg',
	        'credit': 'Sentinel-2 cloudless 2023, EOX (Copernicus)'},
	'pnoa': {'name': 'PNOA orthophoto (IGN)', 'max': 20, 'credit': 'PNOA © Instituto Geográfico Nacional',
	         'wms': 'https://www.ign.es/wms-inspire/pnoa-ma?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&STYLES=&'
	                'LAYERS=OI.OrthoimageCoverage&CRS=EPSG:3857&WIDTH=256&HEIGHT=256&FORMAT=image/jpeg&BBOX={bbox}'},
}
TILE = 256
WEB_MERCATOR = 20037508.342789244


def map_view(bounds, zoom, overlay, base='osm', opacity=0.85, marker=None, max_pixels=4096 ** 2):
	"""A PNG (data: URL) of a view of the interactive map: the tiles of the base map BASE (see BASEMAPS) and, over
	them with OPACITY, those of OVERLAY (the template {z}/{x}/{y} of the tiles of Earth Engine), over BOUNDS
	[w, s, e, n] at ZOOM, with MARKER ([lon, lat]) circled and the credits of the base map."""
	import io
	from concurrent.futures import ThreadPoolExecutor
	from PIL import Image, ImageDraw, ImageFont
	w, s, e, n = bounds
	zoom = int(zoom)
	(x0, y0), (x1, y1) = _pixel(w, n, zoom), _pixel(e, s, zoom)
	width, height = int(round(x1 - x0)), int(round(y1 - y0))
	if width <= 0 or height <= 0 or width * height > max_pixels:
		raise ValueError('the view of the map is too big: zoom in')
	tiles = [(tx, ty) for tx in range(int(x0 // TILE), int((x1 - 1) // TILE) + 1)
	         for ty in range(int(y0 // TILE), int((y1 - 1) // TILE) + 1)]
	b = BASEMAPS.get(base) or BASEMAPS['osm']

	def get(url):
		try:
			req = urllib.request.Request(url, headers={'User-Agent': f'MonitorEO/{__version__} '
			                                                        '(+https://github.com/monitoreo-obsnev/monitoreo)'})
			with urllib.request.urlopen(req, timeout=30) as r:
				return Image.open(io.BytesIO(r.read())).convert('RGBA')
		except Exception:  # a missing tile leaves its place empty
			return None

	def urls(tx, ty):
		z = min(zoom, b['max'])  # beyond the zoom of the base map: its tile of a lower zoom, cut and enlarged
		k = 2 ** (zoom - z)
		if 'wms' in b:
			size = 2 * WEB_MERCATOR / 2 ** zoom
			bbox = f'{-WEB_MERCATOR + tx * size},{WEB_MERCATOR - (ty + 1) * size},{-WEB_MERCATOR + (tx + 1) * size},' \
			       f'{WEB_MERCATOR - ty * size}'
			base_url = b['wms'].format(bbox=bbox)
		else:
			base_url = b['tiles'].format(z=z, x=tx // k, y=ty // k)
		return base_url, overlay.format(z=zoom, x=tx, y=ty), k, (tx % k, ty % k)

	with ThreadPoolExecutor(8) as pool:
		got = list(pool.map(lambda t: (t, urls(*t)), tiles))
		images = list(pool.map(lambda g: (get(g[1][0]), get(g[1][1])), got))
	canvas = Image.new('RGBA', (width, height), (240, 240, 240, 255))
	for ((tx, ty), (_, _, k, (dx, dy))), (base_tile, over) in zip(got, images):
		at = (int(tx * TILE - x0), int(ty * TILE - y0))
		if base_tile is not None:
			if k > 1:
				part = TILE // k
				base_tile = base_tile.crop((dx * part, dy * part, (dx + 1) * part, (dy + 1) * part)).resize((TILE, TILE))
			canvas.paste(base_tile, at)
		if over is not None:
			alpha = over.getchannel('A').point(lambda v: int(v * opacity))
			over.putalpha(alpha)
			layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
			layer.paste(over, at)
			canvas = Image.alpha_composite(canvas, layer)
	draw = ImageDraw.Draw(canvas)
	if marker:
		mx, my = _pixel(marker[0], marker[1], zoom)
		mx, my = mx - x0, my - y0
		draw.ellipse((mx - 8, my - 8, mx + 8, my + 8), outline=(255, 138, 0, 255), width=3)
	credit = f"{b['credit']} · MonitorEO, Google Earth Engine"
	for size in (13, 11, 9):  # the credits fit in the width of the view
		try:
			font = ImageFont.load_default(size=size)
		except TypeError:  # Pillow before 10.1
			font = ImageFont.load_default()
		tw, th = draw.textbbox((0, 0), credit, font=font)[2:]
		if tw <= width - 10:
			break
	else:
		credit = b['credit']
		tw, th = draw.textbbox((0, 0), credit, font=font)[2:]
	draw.rectangle((width - tw - 10, height - th - 8, width, height), fill=(255, 255, 255, 210))
	draw.text((width - tw - 5, height - th - 5), credit, fill=(40, 40, 40, 255), font=font)
	buf = io.BytesIO()
	canvas.convert('RGB').save(buf, 'PNG', optimize=True)
	return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


def _pixel(lon, lat, zoom):
	"""The pixel of the world at ZOOM (Web Mercator, tiles of 256) of a point."""
	n = TILE * 2 ** zoom
	lat = max(min(lat, 85.0511), -85.0511)
	return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def map_style(tool, args, result):
	"""How the map of the GeoTIFF of a result is drawn, as in the other tools of MonitorEO: {'band' (its number),
	'classes' ([{'value', 'label', 'color', 'dnbr_min', 'dnbr_max'}])} for the burn severity, its band severity with
	the colours of the classes of the USGS; {'band', 'min', 'max', 'palette'} for the RBR (its band rbr, with the
	reversed diverging ramp of the Earth Engine app) and the other results with colours (their first band); None for
	those without them."""
	if not isinstance(result, dict):
		return None
	if tool == 'burn_severity':  # as in the QGIS plugin: fire.map_style
		return fire.map_style(result.get('bands'))
	if result.get('palette'):
		return {'band': 1, **{k: result.get(k) for k in ('min', 'max', 'palette')}}
	return None


def class_label(c):
	"""The label of a class of the burn severity in a legend, with its dNBR: «Low severity (dNBR 0.1 to 0.27)», as in
	the QGIS plugin (fire.class_label)."""
	return fire.class_label(c)


def tif_preview(path, palette=None, vmin=None, vmax=None, width=900, band=1, classes=None):
	"""A PNG (data: URL) of the band BAND (default: the first) of a GeoTIFF with the colours PALETTE from VMIN to VMAX
	(default: its percentiles 5 and 95) or, with CLASSES ([{'value', 'color' ('#rrggbb')}]), with the colour of each
	class; at most WIDTH pixels wide; None without GDAL or matplotlib, or if it cannot read it."""
	try:
		import io
		import numpy as np
		from matplotlib import colors
		from matplotlib import pyplot as plt
		from osgeo import gdal
		gdal.UseExceptions()
		ds = gdal.Open(path)
		b = ds.GetRasterBand(band)
		step = max(1, int(math.ceil(ds.RasterXSize / width)))
		a = b.ReadAsArray(buf_xsize=ds.RasterXSize // step or 1, buf_ysize=ds.RasterYSize // step or 1)
		nodata = b.GetNoDataValue()
		a = np.ma.masked_invalid(np.ma.masked_equal(a, nodata) if nodata is not None else a)
		if a.count() == 0:
			return None
		buf = io.BytesIO()
		if classes:  # the colour of each class (nearest pixel), transparent outside them
			rgba = _colours(a.astype('float64').filled(np.nan), {'type': 'categories', 'classes': classes})
			plt.imsave(buf, rgba, format='png')
			return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
		lo, hi = (vmin, vmax) if vmin is not None and vmax is not None else np.percentile(a.compressed(), [5, 95])
		cmap = colors.LinearSegmentedColormap.from_list('p', ['#' + c.lstrip('#') for c in palette or
		                                                      ['440154', '21918c', 'fde725']])
		cmap.set_bad(alpha=0)
		plt.imsave(buf, a, cmap=cmap, vmin=lo, vmax=hi, format='png')
		return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
	except Exception:  # a preview never breaks a result
		return None


def view_facts(item):
	"""The facts of a view of the interactive map (an item with 'view': bounds and base map)."""
	view = item.get('view')
	if not view:
		return []
	w, s, e, n = view['bounds']
	return [('Map view', f'longitude {_num(w)} to {_num(e)}, latitude {_num(s)} to {_num(n)}'),
	        ('Base map', (BASEMAPS.get(view.get('base')) or BASEMAPS['osm'])['name'])]


def _legend(result):
	colours = ', '.join(f'#{c.lstrip("#")}' for c in result['palette'])
	unit = unit_text(result.get('unit'))
	return (f'<figcaption class="legend"><span>{_num(result.get("min"))}</span>'
	        f'<span class="bar" style="background: linear-gradient(to right, {colours})"></span>'
	        f'<span>{_num(result.get("max"))}{" " + _e(unit) if unit else ""}</span></figcaption>')


def _class_legend(classes):
	items = ''.join(f'<span class="class"><span class="swatch" style="background: {_e(c["color"])}"></span>'
	                f'{_e(class_label(c))}</span>' for c in classes)
	return f'<figcaption class="legend classes">{items}</figcaption>'


def _table(labels, rows):
	head = ''.join(f'<th>{_e(x)}</th>' for x in labels)
	body = ''.join('<tr>' + ''.join(f'<td{" class=text" if isinstance(v, str) and not _numeric(v) else ""}>'
	                                f'{_e(v)}</td>' for v in r) + '</tr>' for r in rows)
	return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _entry(variable, sensor):
	if not variable:
		return None
	try:
		return services.describe_variable(variable, sensor)  # with its name and pixel filters
	except (KeyError, ValueError):
		return None


def _stat(s):
	s = str(s)
	m = re.fullmatch(r'p(\d+)', s)
	return f'percentile {m.group(1)}' if m else STATS.get(s, s)


def _num(v, digits=4):
	"""A number as written in English: 1,234 (thousands), 0.1234."""
	if v is None or v == '' or (isinstance(v, float) and math.isnan(v)):
		return '–'
	if isinstance(v, bool):
		return 'yes' if v else 'no'
	if isinstance(v, int) or (isinstance(v, float) and abs(v) >= 1000):
		return f'{v:,.0f}'
	if isinstance(v, float):
		return '0' if v == 0 else f'{v:.{digits}g}'
	return str(v)


def _numeric(s):
	return bool(re.fullmatch(r'[-−]?[\d,]+(\.\d+)?(e[-+]?\d+)?|–|yes|no', s))


def _long_date(d):
	return f'{d.day} {MONTHS[d.month - 1]} {d.year}'


def _data_url(path):
	ext = os.path.splitext(path)[1].lower().lstrip('.')
	mime = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'svg': 'image/svg+xml'}.get(ext, f'image/{ext}')
	with open(path, 'rb') as f:
		return f'data:{mime};base64,{base64.b64encode(f.read()).decode()}'


def _e(x):
	return html.escape(str(x), quote=True)
