"""Charts of the time series (PNG), with matplotlib but without pyplot, so they can be drawn inside QGIS too."""

import datetime as dt
import io
import textwrap


def time_series_png(rows, path=None, title=None, ylabel=None, width=10, height=4.5, dpi=150):
	"""PNG (bytes) of the time series ROWS ([{region, date, value, ...}]): a line per region, with gaps where a step
	has no value. It is also written to PATH if given."""
	from matplotlib.figure import Figure

	fig = Figure(figsize=(width, height), dpi=dpi)
	ax = fig.add_subplot()
	regions = []
	for r in rows:
		if r['region'] not in regions:
			regions.append(r['region'])
	for name in regions:
		pts = sorted((dt.date.fromisoformat(r['date']), r.get('value')) for r in rows if r['region'] == name)
		x = [p[0] for p in pts]
		y = [p[1] if p[1] is not None else float('nan') for p in pts]
		ax.plot(x, y, marker='o', markersize=3, linewidth=1.2, label=name)
	if title:
		ax.set_title(title, fontsize=11)
	if ylabel:
		ax.set_ylabel(ylabel)
	ax.grid(alpha=0.3)
	if len(regions) > 1:
		ax.legend(fontsize=8, frameon=False)
	fig.autofmt_xdate()
	fig.tight_layout()
	return _png(fig, path)


def _png(fig, path=None):
	from matplotlib.backends.backend_agg import FigureCanvasAgg
	buf = io.BytesIO()
	FigureCanvasAgg(fig).print_png(buf)
	png = buf.getvalue()
	if path:
		with open(path, 'wb') as f:
			f.write(png)
	return png


def trends_png(yearly, trends, path=None, title=None, ylabel=None, dpi=120):
	"""PNG (bytes) of the yearly values of each part of the year (YEARLY: [{region, part, year, value}]) with the Sen
	line of its trend (TRENDS: rows of monitoreo.trends.trend_rows), a panel per part and a colour per region."""
	from matplotlib.figure import Figure
	from matplotlib.ticker import MaxNLocator

	parts = sorted({t['part'] for t in trends})
	regions = []
	for t in trends:
		if t['region'] not in regions:
			regions.append(t['region'])
	cols = min(len(parts), 4)
	rows_n = -(-len(parts) // cols)
	width = max(3.2 * cols + 0.5, 8)
	fig = Figure(figsize=(width, 2.5 * rows_n + 0.8 + (0.6 if cols == 1 else 0)), dpi=dpi)
	for i, part in enumerate(parts):
		ax = fig.add_subplot(rows_n, cols, i + 1)
		label = ''
		for j, region in enumerate(regions):
			color = f'C{j % 10}'
			pts = sorted((r['year'], r['value']) for r in yearly
			             if r['region'] == region and r['part'] == part and r['value'] is not None)
			if pts:
				ax.plot([p[0] for p in pts], [p[1] for p in pts], 'o', ms=3, color=color, label=region)
			t = next((t for t in trends if t['region'] == region and t['part'] == part), None)
			if t and t['slope'] is not None and pts:
				x0, x1 = pts[0][0], pts[-1][0]
				ax.plot([x0, x1], [t['intercept'], t['intercept'] + t['slope'] * (x1 - x0)], '--', color=color, lw=1)
				label = label or t['label']
				if len(regions) == 1:
					label += f"  {t['slope']:+.3g}/year, p={t['p_value']:.2g}"
		ax.set_title(label, fontsize=8)
		ax.xaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))  # whole years
		ax.tick_params(labelsize=7)
		ax.grid(alpha=0.3)
	if len(regions) > 1:
		fig.axes[0].legend(fontsize=7, frameon=False)
	if title:
		fig.suptitle(textwrap.fill(title, int(width * 11)), fontsize=10)
	if ylabel:
		fig.supylabel(ylabel, fontsize=9)
	fig.tight_layout()
	return _png(fig, path)


def comparison_png(profile, labels, path=None, title=None, ylabel=None, names=('reference period', 'other period'),
                   width=10, height=4.5, dpi=150):
	"""PNG (bytes) of the comparison of two periods (PROFILE: rows of monitoreo.trends.profile): the mean of each part
	of the year in the reference period (blue, circles, solid) and in the other (red, squares, dashed), or a colour per
	region if there are several. LABELS: {part: name}."""
	from matplotlib.figure import Figure

	fig = Figure(figsize=(width, height), dpi=dpi)
	ax = fig.add_subplot()
	regions = []
	for r in profile:
		if r['region'] not in regions:
			regions.append(r['region'])
	parts = sorted({r['part'] for r in profile})
	x = list(range(len(parts)))
	for j, region in enumerate(regions):
		rows = {r['part']: r for r in profile if r['region'] == region}
		for k, (key, style, marker, name) in enumerate((('reference', '-', 'o', names[0]), ('other', '--', 's', names[1]))):
			y = [rows[p][key] if p in rows and rows[p][key] is not None else float('nan') for p in parts]
			color = ('C0', 'C3')[k] if len(regions) == 1 else f'C{j % 10}'
			lab = name if len(regions) == 1 else f'{region} · {name}'
			ax.plot(x, y, style, marker=marker, ms=4 if len(parts) > 1 else 7, lw=1.4, color=color, label=lab)
			if len(parts) == 1 and y[0] == y[0]:
				ax.annotate(f'{y[0]:.4g}', (0, y[0]), textcoords='offset points', xytext=(10, -3), fontsize=8, color=color)
	if len(parts) == 1:
		ax.set_xlim(-1, 1)
	ax.set_xticks(x)
	ax.set_xticklabels([labels.get(p, str(p)) for p in parts], rotation=45 if len(parts) > 12 else 0, fontsize=8)
	if title:
		ax.set_title(title, fontsize=11)
	if ylabel:
		ax.set_ylabel(ylabel)
	ax.grid(alpha=0.3)
	ax.legend(fontsize=8, frameon=False)
	fig.tight_layout()
	return _png(fig, path)


def areas_png(rows, colours=None, path=None, title=None, dpi=120, max_regions=6):
	"""PNG (bytes) of the hectares of each class (ROWS: [{region, label, ha, percent}], see monitoreo.classes): a panel
	of horizontal bars per feature (the first MAX_REGIONS; also for features with the same name), each class with its
	colour (COLOURS: {label: 'rrggbb'}) and its %, the classes without area left out."""
	from matplotlib.figure import Figure

	features = []  # the rows of each feature: a new one where the region changes or a class comes again
	for r in rows:
		if not features or r['region'] != features[-1][0]['region'] or any(r['label'] == q['label'] for q in features[-1]):
			features.append([])
		features[-1].append(r)
	features = features[:max_regions]
	shown = [[r for r in f if r.get('ha')] for f in features]
	n = max(1, max((len(v) for v in shown), default=1))
	fig = Figure(figsize=(9, 1.2 + 0.32 * n * len(features)), dpi=dpi)
	for i, f in enumerate(features):
		ax = fig.add_subplot(len(features), 1, i + 1)
		rs = list(reversed(shown[i]))
		ax.barh([textwrap.shorten(str(r['label']), 45) for r in rs], [r['ha'] for r in rs],
		        color=[f"#{(colours or {}).get(r['label'], '6baed6')}" for r in rs], edgecolor='#555', linewidth=0.4)
		for y, r in enumerate(rs):
			if r.get('percent') is not None:
				ax.text(r['ha'], y, f" {r['percent']:.1f} %", va='center', fontsize=8)
		ax.set_xlabel('ha' if i == len(features) - 1 else '')
		ax.tick_params(labelsize=8)
		ax.grid(axis='x', alpha=0.3)
		ax.margins(x=0.15)
		if len(features) > 1:
			ax.set_title(str(f[0]['region']), fontsize=9, loc='left')
	if title:
		fig.suptitle(textwrap.fill(title, 100), fontsize=10)
	fig.tight_layout()
	return _png(fig, path)


def sankey_png(flows, colours=None, path=None, title=None, names=('', ''), dpi=120):
	"""PNG (bytes) of a Sankey diagram of FLOWS ([(from, to, hectares)]): the classes of the first year on the left and
	those of the other on the right, each with its colour (COLOURS: {class: 'rrggbb'}), with a band of each flow
	between them, as wide as its hectares; NAMES, the titles of both columns (the years)."""
	from matplotlib.figure import Figure
	from matplotlib.patches import PathPatch, Rectangle
	from matplotlib.path import Path

	flows = [(a, b, h) for a, b, h in flows if h and h > 0]
	order = list(colours or {})  # both columns in the order of the classes of COLOURS, then the others
	pos = lambda n: (order.index(n) if n in order else len(order), str(n))
	left = sorted(dict.fromkeys(a for a, _, _ in flows), key=pos)
	right = sorted(dict.fromkeys(b for _, b, _ in flows), key=pos)
	total = sum(h for _, _, h in flows) or 1.0
	gap = 0.02
	# the height of all the classes, without the gaps of the longest column: the same hectares, the same height in both
	# columns and in the bands
	k = 1 - gap * (max(len(left), len(right), 1) - 1)
	fig = Figure(figsize=(9, 5.5), dpi=dpi)
	ax = fig.add_subplot()

	def column(nodes, side):
		out, y = {}, 1.0
		for n in nodes:
			h = sum(f[2] for f in flows if f[side] == n) / total * k
			out[n] = [y - h, y]
			y -= h + gap
		return out

	ly, ry = column(left, 0), column(right, 1)
	colour = lambda n: f"#{(colours or {}).get(n, '9e9e9e')}"
	lpos, rpos = {n: v[1] for n, v in ly.items()}, {n: v[1] for n, v in ry.items()}
	for a, b, h in sorted(flows, key=lambda f: (left.index(f[0]), right.index(f[1]))):
		w = h / total * k
		y0, y1 = lpos[a], rpos[b]
		lpos[a] -= w
		rpos[b] -= w
		verts = [(0.1, y0), (0.5, y0), (0.5, y1), (0.9, y1), (0.9, y1 - w), (0.5, y1 - w), (0.5, y0 - w), (0.1, y0 - w),
		         (0.1, y0)]
		codes = [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4, Path.LINETO, Path.CURVE4, Path.CURVE4, Path.CURVE4,
		         Path.CLOSEPOLY]
		ax.add_patch(PathPatch(Path(verts, codes), facecolor=colour(a), alpha=0.45, edgecolor='none'))
	for nodes, x, align in ((ly, 0.08, 'right'), (ry, 0.92, 'left')):
		for n, (lo, hi) in nodes.items():
			ax.add_patch(Rectangle((0.08 if x < 0.5 else 0.9, lo), 0.02, hi - lo, facecolor=colour(n), edgecolor='#444',
			                       linewidth=0.4))
			ha_ = sum(f[2] for f in flows if f[0 if x < 0.5 else 1] == n)
			ax.text(x - 0.005 if x < 0.5 else x + 0.005, (lo + hi) / 2, f'{n} ({ha_:,.0f} ha)', ha=align, va='center',
			        fontsize=8)
	ax.text(0.09, 1.03, names[0], ha='center', fontsize=10, fontweight='bold')
	ax.text(0.91, 1.03, names[1], ha='center', fontsize=10, fontweight='bold')
	ax.set_xlim(-0.35, 1.35)
	ax.set_ylim(-0.02, 1.08)
	ax.axis('off')
	if title:
		ax.set_title(textwrap.fill(title, 100), fontsize=10)
	fig.tight_layout()
	return _png(fig, path)


def zones_png(rows, stats, path=None, title=None, ylabel=None, xlabel=None, dpi=120):
	"""PNG (bytes) of the statistics of each zone (ROWS of region_stats with zones: zone_label and STATS): the median
	(or else the mean, or the first statistic) of each zone with the band of its percentiles 25 and 75 (or else 5 and
	95) when they are there, named in the legend, a line per region."""
	from matplotlib.figure import Figure

	mid = next((s for s in ('p50', 'median', 'mean') if s in stats), stats[0])
	lo, hi = ('p25', 'p75') if {'p25', 'p75'} <= set(stats) else ('p5', 'p95') if {'p5', 'p95'} <= set(stats) else \
		(None, None)
	fig = Figure(figsize=(9, 4.5), dpi=dpi)
	ax = fig.add_subplot()
	regions = list(dict.fromkeys(r['region'] for r in rows))
	labels = list(dict.fromkeys(r['zone_label'] for r in rows))
	for g in regions:
		rs = [r for r in rows if r['region'] == g]
		x = [labels.index(r['zone_label']) for r in rs]
		y = [r.get(mid) if r.get(mid) is not None else float('nan') for r in rs]
		line = ax.plot(x, y, marker='o', linewidth=1.4, label=f'{g}: {mid}' if len(regions) > 1 else mid)[0]
		if lo:
			ax.fill_between(x, [r.get(lo) if r.get(lo) is not None else float('nan') for r in rs],
			                [r.get(hi) if r.get(hi) is not None else float('nan') for r in rs],
			                color=line.get_color(), alpha=0.18, label=f'{lo} to {hi}' if g == regions[0] else None)
	ax.set_xticks(range(len(labels)))
	ax.set_xticklabels([textwrap.shorten(str(l), 22) for l in labels], rotation=20, ha='right', fontsize=8)
	if xlabel:
		ax.set_xlabel(xlabel)
	if ylabel:
		ax.set_ylabel(ylabel)
	ax.grid(alpha=0.3)
	ax.legend(fontsize=8, frameon=False)
	if title:
		ax.set_title(textwrap.fill(title, 100), fontsize=10)
	fig.tight_layout()
	return _png(fig, path)


def transect_png(rows, path=None, title=None, ylabel=None, dpi=120):
	"""PNG (bytes) of a profile along a line (ROWS of transect: distance_m, value, elevation): the variable against the
	distance, and the elevation in grey on a second axis."""
	from matplotlib.figure import Figure

	fig = Figure(figsize=(9, 4.2), dpi=dpi)
	ax = fig.add_subplot()
	x = [r['distance_m'] / 1000 for r in rows]
	if any(r.get('elevation') is not None for r in rows):
		ax2 = ax.twinx()
		z = [r['elevation'] if r.get('elevation') is not None else float('nan') for r in rows]
		ax2.fill_between(x, z, min((v for v in z if v == v), default=0), color='#bdbdbd', alpha=0.5, linewidth=0)
		ax2.set_ylabel('Elevation (m)', color='#777')
		ax2.tick_params(colors='#777', labelsize=8)
		ax.set_zorder(ax2.get_zorder() + 1)
		ax.patch.set_visible(False)
	ax.plot(x, [r['value'] if r.get('value') is not None else float('nan') for r in rows], color='#1f77b4',
	        linewidth=1.5, marker='.', markersize=3)
	ax.set_xlabel('Distance along the line (km)')
	if ylabel:
		ax.set_ylabel(ylabel)
	ax.grid(alpha=0.3)
	if title:
		ax.set_title(textwrap.fill(title, 100), fontsize=10)
	fig.tight_layout()
	return _png(fig, path)
