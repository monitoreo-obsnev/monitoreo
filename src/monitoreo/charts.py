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
					label += f"  {t['slope']:+.3g}/año, p={t['p_value']:.2g}"
		ax.set_title(label, fontsize=8)
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


def comparison_png(profile, labels, path=None, title=None, ylabel=None, names=('referencia', 'otro periodo'),
                   width=10, height=4.5, dpi=150):
	"""PNG (bytes) of the comparison of two periods (PROFILE: rows of monitoreo.trends.profile): the mean of each part
	of the year in the reference period and in the other, a pair of lines per region. LABELS: {part: name}."""
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
		for key, style, name in (('reference', '-', names[0]), ('other', '--', names[1])):
			y = [rows[p][key] if p in rows and rows[p][key] is not None else float('nan') for p in parts]
			lab = name if len(regions) == 1 else f'{region} · {name}'
			ax.plot(x, y, style, marker='o', ms=3, lw=1.4, color=f'C{j % 10}', label=lab)
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
