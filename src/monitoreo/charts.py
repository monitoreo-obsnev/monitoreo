"""Charts of the time series (PNG), with matplotlib but without pyplot, so they can be drawn inside QGIS too."""

import datetime as dt
import io


def time_series_png(rows, path=None, title=None, ylabel=None, width=10, height=4.5, dpi=150):
	"""PNG (bytes) of the time series ROWS ([{region, date, value, ...}]): a line per region, with gaps where a step
	has no value. It is also written to PATH if given."""
	from matplotlib.backends.backend_agg import FigureCanvasAgg
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
	buf = io.BytesIO()
	FigureCanvasAgg(fig).print_png(buf)
	png = buf.getvalue()
	if path:
		with open(path, 'wb') as f:
			f.write(png)
	return png
