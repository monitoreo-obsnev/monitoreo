"""The icon of the app of the assistant: the logo of MonitorEO of the QGIS plugin (qgis/monitoreo_qgis/icon.png, a
rising and falling green line and a yellow sun on a dark teal rounded square), drawn again at a large size with its
geometry and its colours, and with transparent corners. It writes, next to this file:

    monitoreo-assistant.png    512 px, for Linux (the .desktop of the installer of Ubuntu)
    monitoreo-assistant.ico    16 to 256 px, for Windows (the shortcut of the installer of Windows)
    monitoreo-assistant.icns   16 to 1024 px, for macOS (the app of the installer of macOS; only on a Mac, with iconutil)

    python installer/icons/make_icons.py      (needs Pillow)

The installers download them from main, as environment.yml.
"""

import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
TEAL, GREEN, SUN = (31, 78, 95, 255), (123, 211, 137, 255), (245, 197, 66, 255)
# the geometry of icon.png, in its 64 px (measured on it): the square, the sun, and the line, three cubic Bézier
# curves (start, peak, trough and end, with flat tangents at the peak and the trough)
SQUARE, RADIUS = (3, 3, 61, 61), 9
SUN_CENTRE, SUN_RADIUS = (46.5, 15.5), 4.4
LINE = [((8.9, 41.6), (9.72, 39.53), (15.01, 30.71), (18.93, 30.71)),
        ((18.93, 30.71), (23.99, 30.71), (31.83, 45.64), (37.68, 45.64)),
        ((37.68, 45.64), (42.1, 45.64), (50.97, 27.12), (55.9, 22.2))]
LINE_WIDTH = 2.8


def curve(steps):
	"""STEPS points of each curve of LINE."""
	out = []
	for (x0, y0), (x1, y1), (x2, y2), (x3, y3) in LINE:
		for i in range(steps + 1):
			t = i / steps
			u = 1 - t
			out.append((u ** 3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t ** 3 * x3,
			            u ** 3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t ** 3 * y3))
	return out


def icon(size, scale=8):
	"""The icon at SIZE px (drawn at SCALE times and reduced, for smooth edges)."""
	big = size * scale
	k = big / 64
	im = Image.new('RGBA', (big, big), (0, 0, 0, 0))
	d = ImageDraw.Draw(im)
	d.rounded_rectangle([c * k for c in SQUARE], radius=RADIUS * k, fill=TEAL)
	(cx, cy), r = SUN_CENTRE, SUN_RADIUS
	d.ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k], fill=SUN)
	r = LINE_WIDTH * k / 2
	for x, y in curve(steps=max(32, 2 * size)):  # a round brush along the line: smooth sides and round ends
		d.ellipse([x * k - r, y * k - r, x * k + r, y * k + r], fill=GREEN)
	return im.reduce(scale)  # the mean of each SCALE x SCALE block: no halos


def main():
	icon(512).save(os.path.join(HERE, 'monitoreo-assistant.png'), optimize=True)
	sizes = (16, 24, 32, 48, 64, 128, 256)  # each one drawn at its size (not reduced from 256 px): sharper
	icon(256).save(os.path.join(HERE, 'monitoreo-assistant.ico'), sizes=[(s, s) for s in sizes],
	               append_images=[icon(s) for s in sizes[:-1]])
	if shutil.which('iconutil'):
		with tempfile.TemporaryDirectory() as tmp:
			iconset = os.path.join(tmp, 'monitoreo-assistant.iconset')
			os.makedirs(iconset)
			for s in (16, 32, 128, 256, 512):
				icon(s).save(os.path.join(iconset, f'icon_{s}x{s}.png'))
				icon(2 * s).save(os.path.join(iconset, f'icon_{s}x{s}@2x.png'))
			subprocess.run(['iconutil', '-c', 'icns', iconset, '-o', os.path.join(HERE, 'monitoreo-assistant.icns')],
			               check=True)
	else:
		print('Without iconutil (macOS) monitoreo-assistant.icns is not written', file=sys.stderr)


if __name__ == '__main__':
	main()
