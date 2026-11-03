"""Printable report of results of MonitorEO in a single HTML file, to open with the browser and print to PDF.

    report.write(items, title='...', question='...', project='...')   -> path of the HTML file

ITEMS are the results of the tools, in the order of the report: {'tool', 'args', 'result'} with the arguments of the
call and its answer (the dictionary of the MCP server or of monitoreo.services), and optionally 'image' (a PNG file
or its data as a data: URL) when the answer does not name its chart or preview. Everything in the report comes from
them and from the catalog: it has no text written by a language model, nor an interpretation of the results. The
charts, maps and logos are embedded in the file, so it can be moved, sent and opened without connection; long tables
go to an annex at the end. The texts are in Spanish, as those of the viewer of results (monitoreo.publish).
"""

import base64
import datetime as dt
import html
import math
import os
import re

from . import __version__, services
from .publish import MONTHS, SENSORS, STEPS, default_title, period_text, python_call, season_text, slug, unit_text

FOLDER = os.path.join(os.path.expanduser(os.environ.get('MONITOREO_OUTPUT') or '~/MonitorEO'), 'informes')
MAX_ROWS = 40  # longer tables go to the annex

TITLES = {'region_stats': 'Estadísticas de {var}, {period}{season}', 'map_layer': 'Mapa de {var}, {period}{season}',
          'trend_map': 'Mapa de la tendencia de {var}, {period}{season}',
          'compare_map': 'Mapa de la diferencia de {var}: {other} menos {period}{season}'}

METHODS = {
	'time_series': 'Para cada paso de tiempo, la métrica temporal de las imágenes del paso en cada píxel y, sobre la '
	               'región, el estadístico espacial de esos valores.',
	'region_stats': 'La métrica temporal de las imágenes del periodo en cada píxel y sus estadísticas sobre la región.',
	'map_layer': 'La métrica temporal de las imágenes del periodo en cada píxel.',
	'trend_table': 'Para cada parte del año, su valor en cada año (el estadístico espacial de la métrica temporal) y '
	               'la tendencia de esos valores a lo largo de los años: prueba de Mann-Kendall (τ, Z y p-valor) y '
	               'pendiente de Sen (cambio por año).',
	'trend_map': 'La tendencia calculada en cada píxel: prueba de Mann-Kendall y pendiente de Sen (cambio por año).',
	'compare_series': 'Para cada parte del año, la media de sus valores en los años de cada periodo y la diferencia '
	                  'entre ambas (otro periodo menos referencia).',
	'compare_map': 'En cada píxel, la métrica temporal del otro periodo menos la del periodo de referencia.',
	'download_image': 'La métrica temporal de las imágenes del periodo en cada píxel, en un GeoTIFF (float32, NoData '
	                  '-9999).',
	'download_trend': 'La tendencia calculada en cada píxel (prueba de Mann-Kendall y pendiente de Sen, cambio por '
	                  'año), en un GeoTIFF con una banda por resultado (NoData -9999).',
	'download_comparison': 'En cada píxel, la métrica temporal del otro periodo menos la del periodo de referencia, en '
	                       'un GeoTIFF con las bandas diferencia, referencia y otro periodo (NoData -9999).',
	'download_variables': 'Cada variable de la receta, con sus métricas, en un GeoTIFF por variable sobre rejillas '
	                      'alineadas del área de estudio y, si la receta lo pide, de sus ecorregiones.',
	'burn_severity': 'dNBR: NBR del periodo anterior al incendio menos NBR del posterior, con las clases de severidad '
	                 'del USGS (Key y Benson, 2006). Área quemada: dNBR ≥ 0,1.',
}

FILTERS = {'clouds': 'nubes', 'water': 'agua', 'snow': 'nieve', 'aerosols': 'aerosoles'}
STATS = {'mean': 'media', 'median': 'mediana', 'min': 'mínimo', 'max': 'máximo', 'std': 'desviación típica',
         'sum': 'suma', 'count': 'número'}

# the table of each tool: its key in the answer (the first one found), and its columns (key, label); in the labels,
# {u} is the unit of the variable and {uy} that unit per year
TABLES = {
	'time_series': (('rows',), [('region', 'Región'), ('date', 'Fecha'), ('value', 'Valor{u}'),
	                            ('n_images', 'Imágenes'), ('n_pixels', 'Píxeles válidos')]),
	'trend_table': (('trends', 'rows'), [('region', 'Región'), ('label', 'Parte del año'), ('n', 'Años'),
	                                     ('slope', 'Pendiente de Sen{uy}'), ('tau', 'τ de Kendall'),
	                                     ('p_value', 'p-valor'), ('significant', 'Significativa')]),
	'compare_series': (('comparison', 'profile'), [('region', 'Región'), ('label', 'Parte del año'),
	                                               ('reference', 'Referencia{u}'), ('other', 'Otro periodo{u}'),
	                                               ('difference', 'Diferencia{u}'), ('n_reference', 'Años de ref.'),
	                                               ('n_other', 'Años del otro')]),
	'region_stats': ((None,), [('region', 'Región'), ('mean', 'Media{u}'), ('std', 'Desv. típica'), ('min', 'Mín.'),
	                           ('p5', 'P5'), ('p50', 'Mediana'), ('p95', 'P95'), ('max', 'Máx.'),
	                           ('n_pixels', 'Píxeles')]),
	'download_variables': (('files',), [('file', 'Archivo'), ('images', 'Imágenes'), ('pixel_filters', 'Píxeles descartados')]),
	'burn_severity': (('classes',), [('region', 'Región'), ('label', 'Clase de severidad'), ('dnbr_min', 'dNBR desde'),
	                                 ('dnbr_max', 'dNBR hasta'), ('ha', 'Hectáreas')]),
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
code { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .8em; word-break: break-all;
       display: block; background: var(--soft); padding: 6px 8px; }
footer { border-top: 2px solid var(--accent); margin-top: 32px; padding-top: 12px; font-size: .85em; }
footer .logos { display: flex; flex-wrap: wrap; gap: 18px; align-items: center; margin-top: 10px; }
footer .logos img { height: 44px; }
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


def write(items, path=None, title=None, question=None, project=None, names=None, date=None):
	"""Write the report of ITEMS (see the module) to PATH (default: a file in ~/MonitorEO/informes named after the
	title and the time). QUESTION is that of the user, PROJECT the Google Cloud project that computed the results
	and NAMES the names of the protected areas by their WDPA ID. Returns the path."""
	title = title or 'Informe de MonitorEO'
	if not path:
		os.makedirs(FOLDER, exist_ok=True)
		path = os.path.join(FOLDER, f'{slug(title)[:60] or "informe"}_{dt.datetime.now():%Y%m%d-%H%M%S}.html')
	text = html_report(items, title, question, project, names, date)
	with open(path, 'w', encoding='utf-8') as f:
		f.write(text)
	return path


def html_report(items, title, question=None, project=None, names=None, date=None):
	"""The HTML of the report (see write)."""
	date = date or dt.date.today()
	a = services.about('es')
	logos = [_data_url(p) for p in a['logos']]
	annex = []
	sections = [_item(item, i + 1, names or {}, annex) for i, item in enumerate(items)]
	out = ['<!doctype html><html lang="es"><head><meta charset="utf-8">',
	       '<meta name="viewport" content="width=device-width, initial-scale=1">',
	       f'<title>{_e(title)}</title><style>{CSS}</style></head><body><main>',
	       f'<header class="top"><img src="{logos[0]}" alt="MonitorEO-OBSNEV"><div><b>MonitorEO-OBSNEV</b><br>'
	       '<span class="meta">Observatorio de Cambio Global de Sierra Nevada · Universidad de Granada</span></div>'
	       '</header>',
	       '<p class="hint noprint">Para guardarlo en PDF: <b>Imprimir</b> y, como destino, <b>Guardar como PDF</b>. '
	       'Desactiva «Encabezados y pies de página» en las opciones del diálogo de impresión.</p>',
	       f'<h1>{_e(title)}</h1>',
	       f'<p class="meta">{_long_date(date)} · {len(items)} resultado{"s" if len(items) != 1 else ""}'
	       + (f' · calculado en Google Earth Engine con el proyecto {_e(project)}' if project else '') + '</p>']
	if question:
		out.append(f'<div class="question"><b>Consulta:</b> {_e(question)}</div>')
	out.append('<p class="note">Este informe recoge los resultados de los cálculos y cómo se obtuvieron, sin '
	           'interpretarlos. Su interpretación corresponde a personal técnico.</p>')
	out += sections
	if annex:
		out.append('<section class="annex"><h2>Anexo: tablas completas</h2>' + ''.join(annex) + '</section>')
	out.append(f'<footer><p><b>Cómo citar MonitorEO:</b> {_e(a["citation"])}</p>'
	           f'<p>{_e(a["acknowledgements"])}</p>'
	           f'<p class="meta">Generado con MonitorEO {_e(__version__)} · Manual: {_e(a["manual"])}</p>'
	           '<div class="logos">' + ''.join(f'<img src="{u}" alt="">' for u in logos) + '</div></footer>')
	out.append('<button class="print noprint" onclick="window.print()">Imprimir o guardar en PDF</button>')
	out.append('</main></body></html>')
	return '\n'.join(out)


def item_title(tool, args, result=None):
	"""The title in Spanish of the result of a call."""
	if tool in TITLES:
		v = f"{args.get('variable', '')} ({SENSORS.get(args.get('sensor'), args.get('sensor') or '')})"
		other = period_text(args['other_start'], args['other_end']) if args.get('other_start') else ''
		return TITLES[tool].format(var=v, period=period_text(args['start'], args['end']), other=other,
		                           season=season_text(args.get('season')))
	if tool in ('time_series', 'trend_table', 'compare_series', 'burn_severity', 'download_image', 'download_trend',
	            'download_comparison'):
		return default_title(tool, args) + (' (GeoTIFF)' if tool == 'download_image' else '')
	if tool == 'download_variables':
		return f"Variables en GeoTIFF: {args.get('name', '')}" + (' (plan, sin descargar)' if args.get('dry_run') else '')
	return (result or {}).get('title') or tool


def item_facts(tool, args, result=None, names=None):
	"""How a result was computed: [(label, text)] in Spanish."""
	result = result if isinstance(result, dict) else {}
	if tool == 'download_variables':
		return _recipe_facts(args, result, names)
	facts = [('Región', region_text(args.get('region'), names or {}))]
	entry = _entry(args.get('variable') or ('NBR' if tool == 'burn_severity' else None), args.get('sensor') or
	               ('Sentinel-2' if tool == 'burn_severity' else None))
	if entry:
		facts.append(('Variable', f"{entry.get('name', '')} ({entry.get('index', '')})"))
		facts.append(('Sensor', f"{SENSORS.get(entry['sensor'], entry['sensor'])}, píxel de {entry.get('m', '?')} m, "
		                        f"colección {entry.get('col', '')}"))
	if args.get('start') and args.get('end'):
		label = 'Antes del incendio' if tool == 'burn_severity' else \
			'Periodo de referencia' if args.get('other_start') else 'Periodo'
		facts.append((label, period_text(args['start'], args['end']) + season_text(args.get('season'))))
	if args.get('other_start') and args.get('other_end'):
		label = 'Después del incendio' if tool == 'burn_severity' else 'Otro periodo'
		facts.append((label, period_text(args['other_start'], args['other_end']) + season_text(args.get('season'))))
	if tool in ('time_series', 'trend_table', 'compare_series', 'trend_map', 'download_trend'):
		step = args.get('step') or ('annual' if 'trend' in tool else 'monthly')
		facts.append(('Paso', STEPS.get(step, step)))
	if tool in ('trend_map', 'download_trend') and args.get('part'):
		part = int(args['part'])
		facts.append(('Parte del año', MONTHS[part - 1] if args.get('step') == 'monthly' else f'periodo {part}'))
	metric = args.get('metric') or ('median' if tool in ('region_stats', 'map_layer', 'compare_map', 'burn_severity',
	                                                      'download_image', 'download_comparison') else 'mean')
	facts.append(('Métrica temporal', _stat(metric)))
	if tool in ('time_series', 'trend_table', 'compare_series'):
		facts.append(('Estadístico espacial', _stat(args.get('stat') or 'mean')))
	if entry:
		filters = dict(entry.get('pixel_filters') or {})
		filters.update({k: bool(v) for k, v in (args.get('quality') or {}).items() if k in FILTERS})
		on = [FILTERS[k] for k, v in filters.items() if v and k in FILTERS]
		facts.append(('Píxeles descartados', ', '.join(on) if on else 'ninguno'))
	if result.get('scale'):
		facts.append(('Tamaño de píxel del cálculo', f"{_num(result['scale'])} m"))
	if tool == 'trend_table':
		facts.append(('Significativa si', f"p < {_num(args.get('alpha') or 0.05)}"))
	if tool == 'burn_severity' and result.get('burned_ha'):
		burned = result['burned_ha']
		facts.append(('Área quemada', '; '.join(f'{k}: {_num(v)} ha' for k, v in burned.items()) if len(burned) > 1
		              else f'{_num(next(iter(burned.values())))} ha'))
	grid = result.get('grid')
	if isinstance(grid, dict) and grid.get('width'):
		native = result.get('native_resolution')
		res = result.get('resolution') or grid.get('resolution')
		facts.append(('GeoTIFF', f"{_num(grid['width'])} × {_num(grid['height'])} píxeles de {_num(res)} m"
		                         + (f' (los datos, de {_num(native)} m)' if native and native != res else '')
		                         + f", en {grid.get('crs', '')}"))
	if result.get('bands'):
		facts.append(('Bandas', ', '.join(map(str, result['bands']))))
	if result.get('images'):
		facts.append(('Imágenes', _num(result['images'])))
	if tool == 'download_image' and result.get('min') is not None:
		unit = unit_text(result.get('unit'))
		facts.append(('Valores (percentiles 5 y 95)', f"{_num(result['min'])} a {_num(result['max'])}"
		                                              + (f' {unit}' if unit else '')))
	if tool in METHODS:
		facts.append(('Método', METHODS[tool]))
	return facts


def _recipe_facts(args, result, names):
	"""How the variables of a recipe (download_variables) were downloaded."""
	recipe = args.get('recipe') or {}
	facts = [('Área de estudio', region_text(args.get('area'), names or {}))]
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
		facts.append(('Periodo', period_text(*period) + season_text(recipe.get('season'))))
	for name, g in (result.get('grids') or {}).items():
		label = {'study': 'Rejilla del área de estudio', 'ecoregion': 'Rejilla de las ecorregiones'}.get(name, name)
		facts.append((label, f"{_num(g.get('width'))} × {_num(g.get('height'))} píxeles de {_num(g.get('resolution'))} m"
		                     f", {_num(g.get('mb_per_variable'))} MB por variable"))
	if args.get('dry_run'):
		facts.append(('Descarga', 'solo el plan: no se ha descargado nada'))
	elif result:
		facts.append(('Descarga', 'completa' if result.get('done') else
		              f"pendiente: {len(result.get('pending') or [])} exportaciones a Google Drive en marcha"))
		if result.get('folders'):
			facts.append(('Carpetas', '; '.join(map(str, result['folders'].values() if isinstance(result['folders'], dict)
			                                         else result['folders']))))
	facts.append(('Método', METHODS['download_variables']))
	return facts


def item_table(tool, result, args=None):
	"""The table of a result: (columns, rows) with the values already formatted, or None."""
	if tool not in TABLES:
		return None
	keys, cols = TABLES[tool]
	rows = result if keys == (None,) else next((result.get(k) for k in keys if isinstance(result, dict) and
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


def region_text(region, names=None):
	"""A region of the tools (see monitoreo.areas) in Spanish."""
	names = names or {}
	if not isinstance(region, dict):
		return str(region)
	if 'wdpa_id' in region:
		ids = region['wdpa_id'] if isinstance(region['wdpa_id'], list) else [region['wdpa_id']]
		return '; '.join(f'{names[str(i)]} (WDPA {i})' if str(i) in names else f'Espacio protegido WDPA {i}'
		                 for i in ids)
	if 'wdpa_name' in region:
		return f"Espacio protegido «{region['wdpa_name']}»"
	if 'ecoregion_id' in region:
		return f"Ecorregión {region['ecoregion_id']}"
	if 'ecoregion_at' in region:
		lon, lat = region['ecoregion_at']
		return f'Ecorregión del punto {_num(lat)}, {_num(lon)} (lat., lon.)'
	if 'bbox' in region:
		w, s, e, n = region['bbox']
		return f'Rectángulo de longitud {_num(w)} a {_num(e)} y latitud {_num(s)} a {_num(n)}'
	if 'point' in region:
		lon, lat = region['point']
		return f"Círculo de {_num(region.get('buffer') or 0)} m de radio en {_num(lat)}, {_num(lon)} (lat., lon.)"
	if 'file' in region:
		return names.get(str(region['file'])) or f"Archivo {os.path.basename(str(region['file']))}"
	if 'geojson' in region:
		g = region['geojson']
		n = len(g.get('features', [])) if isinstance(g, dict) and g.get('type') == 'FeatureCollection' else 1
		return f'Geometría GeoJSON ({n} elemento{"s" if n != 1 else ""})'
	return str(region)


def _item(item, n, names, annex):
	tool, args, result = item['tool'], item.get('args') or {}, item.get('result')
	title = item.get('title') or item_title(tool, args, result if isinstance(result, dict) else None)
	out = [f'<section class="result"><h2>{n}. {_e(title)}</h2><dl>']
	out += [f'<dt>{_e(k)}</dt><dd>{_e(v)}</dd>' for k, v in item_facts(tool, args, result, names)]
	out.append('</dl>')
	image = item.get('image') or (result.get('chart') or result.get('thumbnail') if isinstance(result, dict) else None)
	if image:
		src = image if str(image).startswith('data:') else _data_url(image) if os.path.exists(image) else None
		if src:
			out.append(f'<figure><img src="{src}" alt="{_e(title)}">')
			if isinstance(result, dict) and result.get('palette'):
				out.append(_legend(result))
			out.append('</figure>')
	table = item_table(tool, result, args)
	if table:
		labels, rows = table
		if len(rows) <= MAX_ROWS:
			out.append(_table(labels, rows))
		else:
			out.append(f'<p class="note">Tabla de {len(rows)} filas: en el anexo (tabla {n}).</p>')
			annex.append(f'<h3>Tabla {n}. {_e(title)}</h3>' + _table(labels, rows))
	files = [result.get(k) for k in ('csv', 'file') if isinstance(result, dict) and result.get(k)]
	if files:
		out.append('<p class="note">Archivos: ' + ' · '.join(_e(f) for f in files) + '</p>')
	call = python_call(tool, args)
	if call:
		out.append(f'<h3>Para reproducirlo en Python</h3><code>import monitoreo.services as mo<br>{_e(call)}</code>')
	out.append('</section>')
	return ''.join(out)


def tif_preview(path, palette=None, vmin=None, vmax=None, width=900):
	"""A PNG (data: URL) of the first band of a GeoTIFF with the colours PALETTE from VMIN to VMAX (default: its
	percentiles 5 and 95), at most WIDTH pixels wide; None without GDAL or matplotlib, or if it cannot read it."""
	try:
		import io
		import numpy as np
		from matplotlib import colors
		from matplotlib import pyplot as plt
		from osgeo import gdal
		gdal.UseExceptions()
		ds = gdal.Open(path)
		band = ds.GetRasterBand(1)
		step = max(1, int(math.ceil(ds.RasterXSize / width)))
		a = band.ReadAsArray(buf_xsize=ds.RasterXSize // step or 1, buf_ysize=ds.RasterYSize // step or 1)
		nodata = band.GetNoDataValue()
		a = np.ma.masked_invalid(np.ma.masked_equal(a, nodata) if nodata is not None else a)
		if a.count() == 0:
			return None
		lo, hi = (vmin, vmax) if vmin is not None and vmax is not None else np.percentile(a.compressed(), [5, 95])
		cmap = colors.LinearSegmentedColormap.from_list('p', ['#' + c.lstrip('#') for c in palette or
		                                                      ['440154', '21918c', 'fde725']])
		cmap.set_bad(alpha=0)
		buf = io.BytesIO()
		plt.imsave(buf, a, cmap=cmap, vmin=lo, vmax=hi, format='png')
		return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
	except Exception:  # a preview never breaks a result
		return None


def _legend(result):
	colours = ', '.join(f'#{c.lstrip("#")}' for c in result['palette'])
	unit = unit_text(result.get('unit'))
	return (f'<figcaption class="legend"><span>{_num(result.get("min"))}</span>'
	        f'<span class="bar" style="background: linear-gradient(to right, {colours})"></span>'
	        f'<span>{_num(result.get("max"))}{" " + _e(unit) if unit else ""}</span></figcaption>')


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
	return f'percentil {m.group(1)}' if m else STATS.get(s, s)


def _num(v, digits=4):
	"""A number as written in Spanish: 1.234 (thousands), 0,1234."""
	if v is None or v == '' or (isinstance(v, float) and math.isnan(v)):
		return '–'
	if isinstance(v, bool):
		return 'sí' if v else 'no'
	if isinstance(v, int) or (isinstance(v, float) and abs(v) >= 1000):
		s = f'{v:,.0f}'
	elif isinstance(v, float):
		s = '0' if v == 0 else f'{v:.{digits}g}'
	else:
		return str(v)
	return s.replace(',', ' ').replace('.', ',').replace(' ', '.')


def _numeric(s):
	return bool(re.fullmatch(r'[-−]?[\d.]+(,\d+)?(e[-+]?\d+)?|–|sí|no', s))


def _long_date(d):
	return f'{d.day} de {MONTHS[d.month - 1]} de {d.year}'


def _data_url(path):
	ext = os.path.splitext(path)[1].lower().lstrip('.')
	mime = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'svg': 'image/svg+xml'}.get(ext, f'image/{ext}')
	with open(path, 'rb') as f:
		return f'data:{mime};base64,{base64.b64encode(f.read()).decode()}'


def _e(x):
	return html.escape(str(x), quote=True)
