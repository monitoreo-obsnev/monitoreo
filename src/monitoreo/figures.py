"""Figures of the maps of MonitorEO for reports and papers (PNG, PDF or SVG), as the maps of cartoee of geemap (Wu,
2020), with matplotlib and without cartopy: the map that Earth Engine makes of the variable (with the outline of the
region) on its geographic extent, with a grid of longitudes and latitudes, a scale bar, a north arrow, the colour ramp
with its unit, the title and the credits of the data.

The map is a thumbnail of Earth Engine in geographic coordinates (EPSG:4326) of the bounds of the region and a margin,
drawn with the aspect of its mean latitude (a degree of longitude is cos(latitude) of a degree of latitude), so that
the shapes and the scale bar are right in the middle of the map (and nearly so in a region of some tens of km).

    Wu, Q. (2020). geemap: A Python package for interactive mapping with Google Earth Engine. Journal of Open Source
      Software, 5(51), 2305. https://doi.org/10.21105/joss.02305
"""

import io
import math
import os
import textwrap

FORMATS = ('.png', '.pdf', '.svg')
KM_PER_DEGREE = 111.32  # of latitude, and of longitude at the equator


def check(path, dpi=None):
	"""ValueError, before Earth Engine, for a file that is not PNG, PDF or SVG, or a resolution out of 72-600 dpi."""
	if path and os.path.splitext(str(path))[1].lower() not in FORMATS:
		raise ValueError(f'{path}: a figure is a PNG (.png), PDF (.pdf) or SVG (.svg)')
	if dpi is not None and not 72 <= int(dpi) <= 600:
		raise ValueError(f'dpi {dpi}: from 72 to 600')


def padded(bounds, margin=0.04):
	"""BOUNDS ([w, s, e, n], degrees) grown by MARGIN of their size on every side."""
	w, s, e, n = bounds
	dx, dy = (e - w) * margin or 0.001, (n - s) * margin or 0.001
	return [w - dx, s - dy, e + dx, n + dy]


def nice(x):
	"""The number 1, 2 or 5 × 10^k closest below X (for the length of a scale bar)."""
	if x <= 0:
		return 1.0
	k = 10 ** math.floor(math.log10(x))
	return max(m * k for m in (1, 2, 5) if m * k <= x)


def scale_bar(bounds, share=0.25):
	"""(length in km, length in degrees of longitude) of a scale bar of about SHARE of the width of BOUNDS, at their
	mean latitude."""
	w, s, e, n = bounds
	per_degree = KM_PER_DEGREE * math.cos(math.radians((s + n) / 2))
	km = nice((e - w) * per_degree * share)
	return km, km / per_degree


def degrees(x, axis):
	"""A longitude (AXIS 'x') or latitude ('y') as 3.45° W, 37.10° N."""
	sign = ('E' if x >= 0 else 'W') if axis == 'x' else ('N' if x >= 0 else 'S')
	return f'{abs(x):.2f}° {sign}'


def map_figure(png, bounds, vis, unit='', title='', credits=(), path=None, dpi=300, width=7.0):
	"""Write to PATH (.png, .pdf or .svg) the figure of the map PNG (bytes of a thumbnail of Earth Engine of BOUNDS,
	[w, s, e, n], in EPSG:4326) coloured with VIS ({'min', 'max', 'palette'}), with its grid, scale bar, north arrow,
	colour ramp with UNIT, TITLE and CREDITS (lines). Returns PATH."""
	from matplotlib.backends.backend_agg import FigureCanvasAgg
	from matplotlib.colorbar import ColorbarBase
	from matplotlib.colors import LinearSegmentedColormap, Normalize
	from matplotlib.figure import Figure
	from matplotlib.image import imread
	from matplotlib.patches import Rectangle
	from matplotlib.ticker import FuncFormatter, MaxNLocator

	w, s, e, n = bounds
	lat0 = (s + n) / 2
	aspect = 1 / max(math.cos(math.radians(lat0)), 0.05)
	img = imread(io.BytesIO(png), format='png')
	ratio = (n - s) * aspect / max(e - w, 1e-9)  # height / width of the map on the page
	map_h = min(width * 0.86 * ratio, 9.0)
	height = map_h + 2.0
	fig = Figure(figsize=(width, height))
	FigureCanvasAgg(fig)
	top = 1 - 0.5 / height
	bottom = 1.4 / height
	ax = fig.add_axes([0.1, bottom, 0.86, top - bottom])
	ax.imshow(img, extent=[w, e, s, n], interpolation='nearest', zorder=1)
	ax.set_xlim(w, e)
	ax.set_ylim(s, n)
	ax.set_aspect(aspect)
	ax.xaxis.set_major_locator(MaxNLocator(5))
	ax.yaxis.set_major_locator(MaxNLocator(5))
	ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: degrees(x, 'x')))
	ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: degrees(y, 'y')))
	ax.tick_params(labelsize=7)
	ax.grid(color='#555', linestyle=':', linewidth=0.5, alpha=0.7, zorder=2)
	# the north arrow, top right
	ax.annotate('N', xy=(0.95, 0.95), xytext=(0.95, 0.80), xycoords='axes fraction', ha='center', va='center',
	            fontsize=10, fontweight='bold', zorder=5,
	            arrowprops={'facecolor': 'black', 'edgecolor': 'black', 'width': 2.5, 'headwidth': 9, 'headlength': 9})
	# the scale bar, bottom left: two halves, black and white
	km, deg = scale_bar(bounds)
	x0, y0, h = w + (e - w) * 0.04, s + (n - s) * 0.05, (n - s) * 0.012
	for i, colour in enumerate(('black', 'white')):
		ax.add_patch(Rectangle((x0 + i * deg / 2, y0), deg / 2, h, facecolor=colour, edgecolor='black', linewidth=0.6,
		                       zorder=5))
	label = f'{km:g} km' if km >= 1 else f'{km * 1000:g} m'
	ax.text(x0 + deg / 2, y0 + h * 1.8, label, ha='center', va='bottom', fontsize=7, zorder=5,
	        bbox={'facecolor': 'white', 'edgecolor': 'none', 'alpha': 0.7, 'pad': 1})
	# the colour ramp, under the map
	cax = fig.add_axes([0.25, bottom - 0.62 / height, 0.56, 0.16 / height])
	cmap = LinearSegmentedColormap.from_list('ramp', ['#' + str(c).lstrip('#') for c in vis['palette']])
	bar = ColorbarBase(cax, cmap=cmap, norm=Normalize(vis['min'], vis['max']), orientation='horizontal')
	bar.ax.tick_params(labelsize=7)
	if unit:
		bar.set_label(unit, fontsize=8)
	if title:
		fig.suptitle(textwrap.fill(title, 95), fontsize=10, y=1 - 0.12 / height, va='top')
	lines = [textwrap.fill(c, 140) for c in credits if c]
	if lines:
		fig.text(0.02, 0.02, '\n'.join(lines), fontsize=5.5, color='#444', va='bottom', ha='left')
	fig.savefig(path, dpi=int(dpi))
	return path
