"""Animations of a variable over a region (timelapses): a frame per time step (a year, a month, 16 days or a day of the
period, within the season if there is one), each the temporal metric of the images of the step on each pixel, as the
maps of MonitorEO, coloured with one colour ramp for every frame so that they can be compared.

Earth Engine computes the colours of each frame on the same grid of web Mercator (ee.data.computePixels, as the
GeoTIFFs of monitoreo.grid: several frames at a time), as the timelapses of geemap (Wu, 2020); this module then writes
on each frame its date, the title, the colour ramp with its unit and the credits of the data, and joins the frames in a
GIF and, for an MP4, converts the GIF with ffmpeg. Not a video of Earth Engine (getVideoThumbURL): the shared account of
MonitorEO cannot make them, and each frame then has the time of a tile. The texts are drawn with Pillow or, without it
(the Python of QGIS), with Qt; the GIF is written by Pillow or, without it, by write_gif (its LZW in pure Python, with a
palette of the colours of the ramp and greys). The pixels of the region without data in a step (no images, or all of
them filtered) are light grey, and those outside the region white, with the outline of the region in black.

    Wu, Q. (2020). geemap: A Python package for interactive mapping with Google Earth Engine. Journal of Open Source
      Software, 5(51), 2305. https://doi.org/10.21105/joss.02305
"""

import concurrent.futures
import datetime as dt
import math
import os
import shutil
import struct

import ee
import numpy as np

from . import composite, maps
from .grid import Grid, _compute

STEPS = ('annual', 'monthly', '16-day', 'daily')
MAX_FRAMES = 120  # frames of an animation
DIMENSIONS = 600  # width or height of the frames of the map (pixels)
MAX_DIMENSIONS = 1200
MIN_WIDTH = 200  # width of the frames of a narrower map (pixels), centred on them, so that their texts fit
FPS = 1  # frames per second: each year (or month) for a second
WORKERS = 6  # frames computed at the same time
NO_DATA = 'd9d9d9'  # the pixels of the region without data in a step
OUTSIDE = 'ffffff'  # outside the region
OUTLINE = '000000'
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
          'November', 'December']
FORMATS = ('.gif', '.mp4')
EARTH = 6378137.0  # radius of web Mercator (m)
TOTALS = ('sum', 'count')  # metrics that grow with the images: that of the whole period is that of all its steps


def check(step, n_frames=None, dimensions=None, fps=None, path=None):
	"""ValueError, before Earth Engine, for a STEP that is not one of STEPS, more than MAX_FRAMES frames or none,
	frames smaller than 64 or bigger than MAX_DIMENSIONS pixels, a speed that is not positive or a file that is not
	.gif or .mp4."""
	if step not in STEPS:
		raise ValueError(f"unknown step {step}: use {', '.join(STEPS)}")
	if n_frames is not None and n_frames > MAX_FRAMES:
		raise ValueError(f'{n_frames} frames: an animation has at most {MAX_FRAMES}; use a longer step (annual, '
		                 'monthly) or a shorter period')
	if n_frames is not None and n_frames < 1:
		raise ValueError('the period (and season) has no time step')
	if dimensions is not None and not 64 <= int(dimensions) <= MAX_DIMENSIONS:
		raise ValueError(f'dimensions {dimensions}: from 64 to {MAX_DIMENSIONS} pixels')
	if fps is not None and not 0 < float(fps) <= 30:
		raise ValueError(f'fps {fps}: frames per second, more than 0 and at most 30')
	if path and os.path.splitext(str(path))[1].lower() not in FORMATS:
		raise ValueError(f'{path}: an animation is a GIF (.gif) or a video (.mp4)')


def label(step, first, after):
	"""The date of a frame of STEP from FIRST to the day before AFTER ('YYYY-MM-DD'): 2021 (the year, or the years of a
	season that crosses the new year: 2021-2022), May 2021, or the days."""
	a = dt.date.fromisoformat(first)
	last = dt.date.fromisoformat(after) - dt.timedelta(days=1)
	if step == 'annual':
		return str(a.year) if a.year == last.year else f'{a.year}-{last.year}'
	if step == 'monthly':
		return f'{MONTHS[a.month - 1]} {a.year}'
	if step == 'daily' or a == last:
		return a.isoformat()
	return f'{a.isoformat()} to {last.isoformat()}'


def frames(col, regions, steps, metric, vis, res=None, bounds=None, dimensions=DIMENSIONS):
	"""The frames (ee.Image, RGB, visualized) of the collection COL of images of a variable ('value') over REGIONS:
	for each (first day, day after the last) of STEPS, the METRIC of its images coloured with VIS, on a light grey
	region (no data) over white, with the outline of the regions. RES (metres of the data) and BOUNDS ([w, s, e, n])
	compute the data coarser than the pixels of the frames on their own grid (see maps.coarse)."""
	outside = ee.Image.constant(0).visualize(palette=[OUTSIDE])
	inside = ee.Image.constant(0).clipToCollection(regions).visualize(palette=[NO_DATA])
	outline = ee.Image().byte().paint(regions, 1, 2).visualize(palette=[OUTLINE])
	out = []
	for a, b in steps:
		value = composite._reduce(col.filterDate(a, b), metric)
		value = maps.coarse(value, res, bounds, dimensions).clipToCollection(regions)
		out.append(outside.blend(inside).blend(value.visualize(**vis)).blend(outline))
	return out


def range_image(col, steps, metric, whole):
	"""The map whose percentiles 5 and 95 colour every frame: WHOLE, that of the whole period or, for a METRIC of TOTALS
	(sum, count), which grows with the images, the median of the frames of STEPS (the METRIC of the images of COL of
	each step): that of the whole period would be that of all the steps, as many times bigger as they are."""
	if str(metric).strip().lower() not in TOTALS:
		return whole
	return ee.ImageCollection.fromImages([composite._reduce(col.filterDate(a, b), metric) for a, b in steps]) \
		.median().rename('value')


def mercator(lon, lat):
	"""(x, y) in web Mercator (EPSG:3857, metres) of a point in degrees."""
	lat = max(min(lat, 85.0), -85.0)
	return EARTH * math.radians(lon), EARTH * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def frame_grid(bounds, dimensions=DIMENSIONS):
	"""The grid of the frames over BOUNDS ([w, s, e, n], degrees), in web Mercator: square pixels, DIMENSIONS of them
	on its longest side."""
	w, s, e, n = bounds
	x0, y0 = mercator(w, s)
	x1, y1 = mercator(e, n)
	res = max(x1 - x0, y1 - y0, 1.0) / int(dimensions)
	return Grid.around('EPSG:3857', res, x0, y0, x1, y1)


def pixel_size(bounds, dimensions=DIMENSIONS, res=None):
	"""The size (m) of the pixels on which Earth Engine computes the frames over BOUNDS ([w, s, e, n], degrees): those
	of the frames (of frame_grid, on the ground at the middle latitude of BOUNDS) or, if bigger, those of the data, RES
	metres (see maps.coarse)."""
	ground = frame_grid(bounds, dimensions).res * math.cos(math.radians((bounds[1] + bounds[3]) / 2))
	return max(ground, float(res or 0))


def fetch_frames(frames_, grid, workers=WORKERS, progress=None):
	"""The frames (uint8 arrays of rows x columns x 3) on GRID, WORKERS at a time; PROGRESS(done, total) after each
	one."""
	def one(frame):
		arr = _compute(ee.Image(frame), grid, (0, 0, grid.width, grid.height))
		return np.clip(np.moveaxis(arr[:3], 0, -1), 0, 255).astype(np.uint8)

	out, done = [None] * len(frames_), 0
	with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:
		jobs = {pool.submit(one, f): i for i, f in enumerate(frames_)}
		for job in concurrent.futures.as_completed(jobs):
			out[jobs[job]] = job.result()
			done += 1
			if progress:
				progress(done, len(frames_))
	return out


def _number(x):
	return f'{x:.3g}' if isinstance(x, (int, float)) else str(x)


def _hex(c):
	c = str(c).lstrip('#')
	return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def ramp(palette, n):
	"""N colours (RGB) along PALETTE, as Earth Engine interpolates it."""
	cols = [_hex(c) for c in palette] or [(0, 0, 0)]
	if len(cols) == 1:
		return cols * n
	out = []
	for i in range(n):
		t = i / max(n - 1, 1) * (len(cols) - 1)
		j = min(int(t), len(cols) - 2)
		f = t - j
		out.append(tuple(round(cols[j][k] + (cols[j + 1][k] - cols[j][k]) * f) for k in range(3)))
	return out


def layout(width, lines=1):
	"""The sizes of the texts of a frame WIDTH pixels wide with LINES lines of credits: (big font, small font, band
	above, ramp, band below)."""
	big, small = max(14, width // 26), max(10, width // 48)
	return big, small, big * 2 + 16, max(10, width // 40), small * 3 + 28 + (max(1, lines) - 1) * (small + 4)


def annotate(frame, i, labels, title, vmin, vmax, palette, unit='', credits=''):
	"""The frame I (uint8 array, rows x columns x 3) with a band above with its date (LABELS, one per frame) and TITLE,
	a progress bar, and a band below with the colour ramp of PALETTE from VMIN to VMAX with its UNIT and the CREDITS of
	the data, all of them, in as many lines as they need (see _wrap): drawn with Pillow or, without it, with Qt (QGIS).
	A map narrower than MIN_WIDTH pixels is centred on a frame of MIN_WIDTH, white around it. ValueError without
	both."""
	texts = (labels[i] if i < len(labels) else '', title, _number(vmin), _number(vmax), unit or '', credits or '',
	         (i + 1) / (len(labels) or 1))
	try:
		import PIL  # noqa: F401
	except ImportError:
		try:
			from qgis.PyQt.QtGui import QImage  # noqa: F401
		except ImportError:
			raise ValueError('an animation needs Pillow, which draws its texts and joins its frames in a GIF: pip install '
			                 'pillow')
		return _annotate_qt(frame, palette, *texts)
	return _annotate_pil(frame, palette, *texts)


def _font(size):
	"""A font of SIZE pixels for Pillow: a TrueType font of the system, or that of Pillow."""
	from PIL import ImageFont
	for name in ('DejaVuSans.ttf', 'Arial.ttf', 'arial.ttf', 'Helvetica.ttc', 'LiberationSans-Regular.ttf',
	             '/System/Library/Fonts/Supplemental/Arial.ttf', '/System/Library/Fonts/Helvetica.ttc',
	             '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'C:/Windows/Fonts/arial.ttf'):
		try:
			return ImageFont.truetype(name, size)
		except OSError:
			continue
	try:
		return ImageFont.load_default(size)  # Pillow >= 10.1
	except TypeError:
		return ImageFont.load_default()


def _cut(width_of, text, width):
	"""TEXT cut with … so that it fits in WIDTH pixels (WIDTH_OF(text): its width)."""
	if width_of(text) <= width:
		return text
	while text and width_of(text + '…') > width:
		text = text[:-1]
	return text + '…'


def _wrap(width_of, text, width):
	"""The lines of TEXT that fit in WIDTH pixels (WIDTH_OF(text): its width), broken at its spaces (a word longer than
	a line, at its letters): nothing is cut."""
	lines, line = [], ''
	for word in str(text or '').split():
		joined = f'{line} {word}' if line else word
		if width_of(joined) <= width:
			line = joined
			continue
		if line:
			lines.append(line)
		while len(word) > 1 and width_of(word) > width:
			k = len(word) - 1
			while k > 1 and width_of(word[:k]) > width:
				k -= 1
			lines.append(word[:k])
			word = word[k:]
		line = word
	return lines + [line] if line else lines


def _annotate_pil(frame, palette, date, title, lo, hi, unit, credits, done):
	from PIL import Image, ImageDraw
	h, m = frame.shape[:2]
	w = max(m, MIN_WIDTH)  # a narrower map, centred
	b, s, top, bar_h, bottom = layout(w)
	big, small = _font(b), _font(s)
	measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
	lines = _wrap(lambda t: measure.textlength(t, font=small), credits, w - 16)
	bottom = layout(w, len(lines))[4]
	canvas = Image.new('RGB', (w, top + h + bottom), 'white')
	canvas.paste(Image.fromarray(frame, 'RGB'), ((w - m) // 2, top))
	d = ImageDraw.Draw(canvas)
	d.text((8, 6), _cut(lambda t: d.textlength(t, font=big), date, w - 16), fill='black', font=big)
	d.text((8, 6 + b + 6), _cut(lambda t: d.textlength(t, font=small), title, w - 16), fill=(60, 60, 60), font=small)
	d.rectangle([0, top + h - 4, int(w * done), top + h - 1], fill=(30, 30, 30))  # progress
	y, x0, x1 = top + h + 6, 8, w - 8
	for k, c in enumerate(ramp(palette, max(x1 - x0, 1))):
		d.line([x0 + k, y, x0 + k, y + bar_h], fill=c)
	d.rectangle([x0, y, x1, y + bar_h], outline=(80, 80, 80))
	ty = y + bar_h + 3
	d.text((x0, ty), lo, fill='black', font=small)
	d.text((x1 - d.textlength(hi, font=small), ty), hi, fill='black', font=small)
	if unit:
		d.text(((w - d.textlength(unit, font=small)) / 2, ty), unit, fill='black', font=small)
	for k, line in enumerate(lines):
		d.text((8, ty + s + 6 + k * (s + 4)), line, fill=(90, 90, 90), font=small)
	return np.asarray(canvas, dtype=np.uint8)


def _annotate_qt(frame, palette, date, title, lo, hi, unit, credits, done):
	from qgis.PyQt.QtCore import QRect, Qt
	from qgis.PyQt.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter
	h, m = frame.shape[:2]
	w = max(m, MIN_WIDTH)  # a narrower map, centred
	b, s, top, bar_h, bottom = layout(w)
	big, small = QFont(), QFont()
	big.setPixelSize(b)
	small.setPixelSize(s)
	fb, fs = QFontMetrics(big), QFontMetrics(small)
	lines = _wrap(fs.horizontalAdvance, credits, w - 16)
	bottom = layout(w, len(lines))[4]
	data = np.ascontiguousarray(frame)
	picture = QImage(data.data, m, h, 3 * m, QImage.Format.Format_RGB888)
	canvas = QImage(w, top + h + bottom, QImage.Format.Format_RGB888)
	canvas.fill(QColor('white'))
	p = QPainter(canvas)
	p.drawImage((w - m) // 2, top, picture)
	left = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
	p.setFont(big)
	p.setPen(QColor('black'))
	p.drawText(QRect(8, 6, w - 16, b + 6), left, _cut(fb.horizontalAdvance, date, w - 16))
	p.setFont(small)
	p.setPen(QColor(60, 60, 60))
	p.drawText(QRect(8, 6 + b + 6, w - 16, s + 6), left, _cut(fs.horizontalAdvance, title, w - 16))
	p.fillRect(0, top + h - 4, int(w * done), 4, QColor(30, 30, 30))  # progress
	y, x0, x1 = top + h + 6, 8, w - 8
	for k, c in enumerate(ramp(palette, max(x1 - x0, 1))):
		p.setPen(QColor(*c))
		p.drawLine(x0 + k, y, x0 + k, y + bar_h)
	p.setPen(QColor(80, 80, 80))
	p.drawRect(x0, y, x1 - x0, bar_h)
	ty = y + bar_h + 3
	p.setPen(QColor('black'))
	p.drawText(QRect(x0, ty, w, s + 6), left, lo)
	p.drawText(QRect(x1 - fs.horizontalAdvance(hi), ty, w, s + 6), left, hi)
	if unit:
		p.drawText(QRect((w - fs.horizontalAdvance(unit)) // 2, ty, w, s + 6), left, unit)
	p.setPen(QColor(90, 90, 90))
	for k, line in enumerate(lines):
		p.drawText(QRect(8, ty + s + 6 + k * (s + 4), w - 16, s + 6), left, line)
	p.end()
	ptr = canvas.constBits()
	if hasattr(ptr, 'setsize'):  # PyQt: a sip.voidptr without its size
		ptr.setsize(canvas.sizeInBytes())
	rows = np.frombuffer(ptr, np.uint8, canvas.sizeInBytes()).reshape(canvas.height(), canvas.bytesPerLine())
	return rows[:, :3 * canvas.width()].reshape(canvas.height(), canvas.width(), 3).copy()


# GIF ----------------------------------------------------------------------------------------------------------------

def palette_of(frames_, colours=()):
	"""(palette, indices): a palette of at most 256 colours (uint8, n x 3) for the RGB arrays FRAMES_ and each frame as
	the index of the nearest colour of its pixels. Their colours, if they are 256 or fewer; else COLOURS (those of the
	colour ramp) and greys (the texts, white, black and the grey of the pixels without data)."""
	packed = [(f[..., 0].astype(np.uint32) << 16) | (f[..., 1].astype(np.uint32) << 8) | f[..., 2] for f in frames_]
	used = np.unique(np.concatenate([np.unique(p) for p in packed]))
	if len(used) <= 256:
		pal = used
	else:
		greys = [(g << 16) | (g << 8) | g for g in range(0, 256, 8)] + [0xffffff, int(NO_DATA, 16)]
		ramp_ = [(r << 16) | (g << 8) | b for r, g, b in colours]
		pal = np.unique(np.array(greys + ramp_, np.uint32))[:256]
	rgb = np.stack([(pal >> 16) & 255, (pal >> 8) & 255, pal & 255], -1).astype(np.int32)
	ucol = np.stack([(used >> 16) & 255, (used >> 8) & 255, used & 255], -1).astype(np.int32)
	nearest = np.empty(len(used), np.uint8)
	for i in range(0, len(used), 4096):  # the nearest colour of the palette to each colour used
		d = ((ucol[i:i + 4096, None, :] - rgb[None, :, :]) ** 2).sum(-1)
		nearest[i:i + 4096] = d.argmin(1)
	return rgb.astype(np.uint8), [nearest[np.searchsorted(used, p)] for p in packed]


def _lzw(data):
	"""The LZW of GIF of the bytes DATA (indices of a palette of 256 colours: minimum code size 8)."""
	clear, end = 256, 257
	out, buf, nbits, size = bytearray(), 0, 0, 9
	table, next_code = {}, 258

	def emit(code):
		nonlocal buf, nbits
		buf |= code << nbits
		nbits += size
		while nbits >= 8:
			out.append(buf & 255)
			buf >>= 8
			nbits -= 8

	emit(clear)
	if not data:
		emit(end)
		return bytes(out + (bytes([buf]) if nbits else b''))
	prefix = data[0]
	get = table.get
	for b in data[1:]:
		key = (prefix << 8) | b
		code = get(key)
		if code is not None:
			prefix = code
			continue
		emit(prefix)
		if next_code < 4096:
			table[key] = next_code
			next_code += 1
			if next_code > (1 << size) and size < 12:
				size += 1
		else:  # the table is full: start again
			emit(clear)
			table.clear()
			get = table.get
			next_code, size = 258, 9
		prefix = b
	emit(prefix)
	emit(end)
	if nbits:
		out.append(buf & 255)
	return bytes(out)


def write_gif(frames_, path, duration=500, colours=()):
	"""Write the RGB arrays FRAMES_ (all of the same size) to the animated GIF PATH, DURATION milliseconds each, looping
	for ever, without Pillow: a palette of their colours (see palette_of, with COLOURS those of the ramp) and the LZW of
	each frame in pure Python."""
	h, w = frames_[0].shape[:2]
	pal, indices = palette_of(frames_, colours)
	table = np.zeros((256, 3), np.uint8)
	table[:len(pal)] = pal
	delay = max(1, int(round(duration / 10)))  # hundredths of a second
	with open(path, 'wb') as f:
		f.write(b'GIF89a' + struct.pack('<HHBBB', w, h, 0xF7, 0, 0) + table.tobytes())
		f.write(b'\x21\xFF\x0BNETSCAPE2.0\x03\x01\x00\x00\x00')  # loop for ever
		for idx in indices:
			f.write(b'\x21\xF9\x04\x04' + struct.pack('<H', delay) + b'\x00\x00')  # not disposed
			f.write(b'\x2C' + struct.pack('<HHHHB', 0, 0, w, h, 0) + b'\x08')
			data = _lzw(np.ascontiguousarray(idx).tobytes())
			for i in range(0, len(data), 255):
				f.write(bytes([len(data[i:i + 255])]) + data[i:i + 255])
			f.write(b'\x00')
		f.write(b'\x3B')
	return path


def save_gif(frames_, path, duration=500, colours=()):
	"""Write the RGB arrays FRAMES_ to the animated GIF PATH with Pillow or, without it, with write_gif: the same
	palette in both (see palette_of, with COLOURS those of the ramp), so that the grey of the pixels without data and the
	colours of the ramp are those of the maps."""
	try:
		from PIL import Image
	except ImportError:
		return write_gif(frames_, path, duration, colours)
	pal, indices = palette_of(frames_, colours)
	table = np.zeros((256, 3), np.uint8)
	table[:len(pal)] = pal
	pics = []
	for idx in indices:
		pic = Image.fromarray(np.ascontiguousarray(idx), 'P')
		pic.putpalette(table.tobytes())
		pics.append(pic)
	pics[0].save(path, save_all=True, append_images=pics[1:], duration=duration, loop=0, optimize=False)
	return path


def _ffmpegs():
	"""The ffmpeg of the system and that of imageio-ffmpeg, those installed."""
	out = [shutil.which('ffmpeg')]
	try:
		import imageio_ffmpeg
		out.append(imageio_ffmpeg.get_ffmpeg_exe())
	except (ImportError, RuntimeError):
		pass
	return [f for f in dict.fromkeys(out) if f]


def to_mp4(gif, mp4):
	"""Convert the GIF to the video MP4 (H.264) with ffmpeg; ValueError (the GIF is kept) if ffmpeg is not installed
	or cannot do it."""
	ffmpegs = _ffmpegs()
	if not ffmpegs:
		raise ValueError(f'an MP4 video needs ffmpeg (https://ffmpeg.org): install it, or ask for a GIF (.gif); the GIF '
		                 f'is {gif}')
	import subprocess  # nosec B404: only ffmpeg, by its full path and without a shell
	why = ''
	for ffmpeg in ffmpegs:
		cmd = [ffmpeg, '-y', '-loglevel', 'error', '-i', gif, '-movflags', 'faststart', '-pix_fmt', 'yuv420p', '-vf',
		       'scale=trunc(iw/2)*2:trunc(ih/2)*2', mp4]
		run = subprocess.run(cmd, capture_output=True, text=True)  # nosec B603: ffmpeg, without a shell
		if run.returncode == 0:
			return mp4
		why = (run.stderr.strip().splitlines() or [f'exit code {run.returncode}'])[-1][:300]
	raise ValueError(f'ffmpeg could not make the MP4 video ({why}); the GIF is {gif}')


def can_draw():
	"""ValueError, before Earth Engine, if there is nothing to draw the texts of the frames (Pillow, or Qt in QGIS)."""
	try:
		import PIL  # noqa: F401
		return
	except ImportError:
		pass
	try:
		from qgis.PyQt.QtGui import QImage  # noqa: F401
	except ImportError:
		raise ValueError('an animation needs Pillow, which draws its texts and joins its frames in a GIF: pip install '
		                 'pillow')


def write(pictures, path, labels, title, vmin, vmax, palette, unit='', credits='', fps=FPS):
	"""Write the animation PATH (.gif, or .mp4 and its .gif) of the frames PICTURES (RGB arrays) with their texts (see
	annotate). Returns the path of the GIF."""
	ext = os.path.splitext(path)[1].lower()
	os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
	gif = path if ext == '.gif' else os.path.splitext(path)[0] + '.gif'
	drawn = [annotate(f, i, labels, title, vmin, vmax, palette, unit, credits) for i, f in enumerate(pictures)]
	save_gif(drawn, gif, int(round(1000 / float(fps))), ramp(palette, 200))
	if ext == '.mp4':
		to_mp4(gif, path)
	return gif
