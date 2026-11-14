"""Animations of a variable (timelapses, services.timelapse and monitoreo.animation), without Earth Engine: the dates of
the frames, the errors before Earth Engine, the GIF written with Pillow and without it (write_gif: its LZW in pure
Python, read again by Pillow), the texts of the frames, the README, the citations, the report, the viewer of results,
the command line and the MCP server. tests/test_ee.py makes one in Earth Engine."""

import json
import os
import types

import numpy as np
import pytest

from monitoreo import animation, readme, references, report, services

REGION = {'bbox': [-3.45, 37.02, -3.30, 37.12]}


def test_the_dates_of_the_frames():
	assert animation.label('annual', '2021-01-01', '2022-01-01') == '2021'
	assert animation.label('annual', '2021-10-01', '2022-06-01') == '2021-2022'  # a season across the new year
	assert animation.label('monthly', '2021-05-01', '2021-06-01') == 'May 2021'
	assert animation.label('16-day', '2021-01-17', '2021-02-02') == '2021-01-17 to 2021-02-01'
	assert animation.label('daily', '2021-03-04', '2021-03-05') == '2021-03-04'


def test_the_errors_before_earth_engine():
	for kwargs, text in (({'step': 'weekly'}, 'unknown step'), ({'dimensions': 5000}, 'from 64 to'),
	                     ({'fps': 0}, 'frames per second'), ({'path': 'a.png'}, r'GIF \(\.gif\) or a video')):
		with pytest.raises(ValueError, match=text):
			services.timelapse(REGION, 'NDVI', 'Sentinel-2', '2020-01-01', '2021-12-31', **kwargs)
	with pytest.raises(ValueError, match='fixed layer'):
		services.timelapse(REGION, 'ELEVATION', 'Copernicus', '2020-01-01', '2021-12-31')
	with pytest.raises(ValueError, match='at most 120'):  # 16 years of months
		services.timelapse(REGION, 'NDVI', 'Modis', '2005-01-01', '2020-12-31', step='monthly')


def test_the_grid_of_the_frames_is_web_mercator():
	g = animation.frame_grid([-3.45, 37.02, -3.30, 37.12], 600)
	assert g.crs == 'EPSG:3857' and max(g.width, g.height) in (600, 601) and min(g.width, g.height) > 300
	x, y = animation.mercator(0, 0)
	assert abs(x) < 1e-6 and abs(y) < 1e-6


def _frames(n=3, h=40, w=60):
	rng = np.random.default_rng(1)
	return [rng.integers(0, 255, (h, w, 3), dtype=np.uint8) for _ in range(n)]


def test_the_lzw_of_gif_is_read_by_pillow(tmp_path):
	Image = pytest.importorskip('PIL.Image')
	# few colours: the GIF has them exactly, in every frame
	colours = np.array([[255, 255, 255], [0, 0, 0], [217, 217, 217], [255, 0, 0], [0, 128, 0]], np.uint8)
	rng = np.random.default_rng(2)
	frames = [colours[rng.integers(0, len(colours), (50, 70))] for _ in range(4)]
	path = animation.write_gif(frames, str(tmp_path / 'few.gif'), 250)
	gif = Image.open(path)
	assert gif.n_frames == 4 and gif.size == (70, 50) and gif.info['duration'] == 250 and gif.info['loop'] == 0
	for i, f in enumerate(frames):
		gif.seek(i)
		assert np.array_equal(np.asarray(gif.convert('RGB')), f), i
	# many colours (a long LZW: its table is full and starts again): each pixel gets the nearest of the palette
	many = _frames(2, 120, 160)
	path = animation.write_gif(many, str(tmp_path / 'many.gif'), 500, animation.ramp(['000000', 'ffffff'], 200))
	gif = Image.open(path)
	assert gif.n_frames == 2
	pal, indices = animation.palette_of(many, animation.ramp(['000000', 'ffffff'], 200))
	for i in range(2):
		gif.seek(i)
		assert np.array_equal(np.asarray(gif.convert('RGB')), pal[indices[i]]), i


def test_the_texts_of_the_frames(tmp_path):
	pytest.importorskip('PIL')
	frame = np.full((300, 400, 3), 200, np.uint8)
	out = animation.annotate(frame, 0, ['2021', '2022'], 'NDVI Sentinel-2', 0.1, 0.8, ['ff0000', '00ff00'], 'unit',
	                         'MonitorEO; Google Earth Engine')
	big, small, top, bar, bottom = animation.layout(400)
	assert out.shape == (top + 300 + bottom, 400, 3) and out.dtype == np.uint8
	assert (out[top:top + 300 - 4] == 200).all()  # the map as it was, above its progress bar
	assert (out[:top] != 255).any()  # its date and title written
	ramp_row = out[top + 300 + 6 + bar // 2, 9:391]
	assert ramp_row[0][0] > 240 > ramp_row[0][1] and ramp_row[-1][1] > 240 > ramp_row[-1][0]  # the colour ramp


def test_every_credit_is_written_on_the_frames():
	"""The credits of the data are written whole, in as many lines as they need (the band below grows), not cut with an
	ellipsis: those of ERA5-Land and of FAO GAUL are long."""
	pytest.importorskip('PIL')
	from PIL import Image, ImageDraw
	credits = ('MonitorEO; Google Earth Engine; Contains modified Copernicus Climate Change Service information '
	           '2021-2023. Neither the European Commission nor ECMWF is responsible for any use that may be made of '
	           'the Copernicus information or data it contains; Source: FAO GAUL 2025 (CC BY 4.0). The designations '
	           'employed and the presentation of material in the map do not imply the expression of any opinion.')
	small = animation._font(animation.layout(600)[1])
	measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
	width = lambda t: measure.textlength(t, font=small)  # noqa: E731
	lines = animation._wrap(width, credits, 600 - 16)
	assert len(lines) > 2 and ' '.join(lines) == credits and all(width(x) <= 600 - 16 for x in lines)
	assert '…' not in ''.join(lines)
	assert animation._wrap(width, 'a ' + 'x' * 400, 100)[0] == 'a'  # a word longer than a line: at its letters
	assert ''.join(animation._wrap(width, 'x' * 400, 100)) == 'x' * 400
	out = animation.annotate(np.full((300, 600, 3), 200, np.uint8), 0, ['2021'], 'PRECIP ERA5-Land', 0, 100,
	                         ['ffffff', '0000ff'], 'mm', credits)
	big, s, top, bar, bottom = animation.layout(600, len(lines))
	assert bottom > animation.layout(600)[4] and out.shape == (top + 300 + bottom, 600, 3)
	last = top + 300 + 6 + bar + 3 + s + 6 + (len(lines) - 1) * (s + 4)
	assert (out[last:last + s, 8:592] != 255).any()  # its last line written


def test_a_narrow_map_on_a_frame_where_its_texts_fit():
	"""A narrow map (a strip of land: 18 x 65 pixels at dimensions=64, 17 x 601 at 600) is centred on a frame
	animation.MIN_WIDTH pixels wide, white around it: its credits, all of them, in a few lines, not a letter or two a
	line in a band below many times the height of the map; and one narrower than its margins can be drawn."""
	pytest.importorskip('PIL')
	from PIL import Image, ImageDraw
	credits = ('MonitorEO; Google Earth Engine; Contains modified USGS Landsat data 2021-2023; Source: FAO GAUL 2025 '
	           '(CC BY 4.0)')
	small = animation._font(animation.layout(animation.MIN_WIDTH)[1])
	measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
	lines = animation._wrap(lambda t: measure.textlength(t, font=small), credits, animation.MIN_WIDTH - 16)
	assert ' '.join(lines) == credits and len(lines) <= 5
	big, s, top, bar, bottom = animation.layout(animation.MIN_WIDTH, len(lines))
	for h, w in ((65, 18), (601, 17), (40, 5), (200, 54)):
		out = animation.annotate(np.full((h, w, 3), 200, np.uint8), 0, ['2021-01-01 to 2021-01-16'], 'NDVI', 0.1, 0.8,
		                         ['ff0000', '00ff00'], '1', credits)
		assert out.shape == (top + h + bottom, animation.MIN_WIDTH, 3), (h, w, out.shape)
		x = (animation.MIN_WIDTH - w) // 2
		assert (out[top:top + h - 4, x:x + w] == 200).all()  # the map, in the middle, above its progress bar
		assert (out[top:top + h - 4, :x] == 255).all() and (out[top:top + h - 4, x + w:] == 255).all()
		last = top + h + 6 + bar + 3 + s + 6 + (len(lines) - 1) * (s + 4)
		assert (out[last:last + s, 8:animation.MIN_WIDTH - 8] != 255).any()  # the last line of its credits
	wide = animation.annotate(np.full((50, 300, 3), 200, np.uint8), 0, ['2021'], 'NDVI', 0.1, 0.8,
	                          ['ff0000', '00ff00'], '1', credits)
	assert wide.shape[1] == 300 and (wide[animation.layout(300)[2]:][:46] == 200).all()  # a wider map: as it was


def test_write_joins_the_frames(tmp_path):
	Image = pytest.importorskip('PIL.Image')
	path = animation.write(_frames(3, 80, 100), str(tmp_path / 'a.gif'), ['2021', '2022', '2023'], 'title', 0, 1,
	                       ['000000', 'ffffff'], '', 'credits', fps=4)
	gif = Image.open(path)
	assert gif.n_frames == 3 and gif.info['duration'] == 250 and gif.size[0] == max(100, animation.MIN_WIDTH)
	path = animation.write(_frames(2, 80, 300), str(tmp_path / 'b.gif'), ['2021', '2022'], 'title', 0, 1,
	                       ['000000', 'ffffff'], '', 'credits', fps=4)
	assert Image.open(path).size[0] == 300


ANSWER = {'file': 'ndvi.gif', 'gif': 'ndvi.gif', 'step': 'annual', 'fps': 2.0, 'dimensions': 600, 'n_frames': 3,
          'min': 0.1, 'max': 0.8, 'palette': ['ff0000', '00ff00'], 'name': 'NDVI Sentinel-2', 'unit': '[unitless]',
          'bounds': REGION['bbox'], 'scale': 10.0,
          'frames': [{'date': f'{y}-01-01', 'end': f'{y + 1}-01-01', 'label': str(y), 'images': n}
                     for y, n in ((2021, 12), (2022, 0), (2023, 9))]}
ARGS = {'region': REGION, 'variable': 'NDVI', 'sensor': 'Sentinel-2', 'start': '2021-01-01', 'end': '2023-12-31',
        'step': 'annual'}


def test_the_readme_and_the_report_of_an_animation(tmp_path):
	gif = tmp_path / 'ndvi.gif'
	gif.write_bytes(b'GIF89a')
	result = dict(ANSWER, file=str(gif), gif=str(gif))
	text = readme.text('timelapse', ARGS, result, computed='2026-11-14T10:00:00+01:00')
	assert 'ndvi.gif: animation (GIF), a frame per time step' in text
	assert '2 2022: 2022-01-01 to the day before 2023-01-01, 0 images' in text
	assert 'Frames: 3, 2 per second; 1 without images (grey)' in text
	assert 'Colours: from 0.1 to 0.8, the same in every frame' in text
	assert 'mo.timelapse(region=' in text and 'Wu, Q. (2020). geemap' in text
	assert report.item_title('timelapse', ARGS) == 'Animation of NDVI (Sentinel-2), 2021-2023'
	assert readme.document('timelapse', ARGS, result) == str(tmp_path / 'ndvi.README.txt')


def test_an_animation_is_cited():
	cited = references.cite('timelapse', ARGS)
	ids = [r['id'] for r in cited['references']]
	assert {'wu2020', 'gorelick2017', 'tucker1979', 'monitoreo'} <= set(ids)
	assert any('Copernicus Sentinel' in c for c in cited['credits'])


def test_an_animation_in_the_viewer_of_results(tmp_path):
	from monitoreo import publish
	PIL = pytest.importorskip('PIL.Image')
	gif = tmp_path / 'ndvi.gif'
	frames = [PIL.new('RGB', (40, 30), c) for c in ('red', 'blue')]
	frames[0].save(gif, save_all=True, append_images=frames[1:], duration=500, loop=0)
	spec = {'title': 'An animation', 'summary': 'Frames', 'region': {'name': 'Sierra Nevada'},
	        'results': [{'tool': 'timelapse', 'args': ARGS, 'result': dict(ANSWER, file=str(gif), gif=str(gif))}]}
	folder = tmp_path / 'report'
	folder.mkdir()
	rep = publish.build(spec, 'an-animation', str(tmp_path), [], None, str(folder))
	r = rep['results'][0]
	assert r['kind'] == 'animation' and r['gif'].startswith('files/') and r['frames'] == ['2021', '2022', '2023']
	assert rep['analyses'] == [{'id': 'animation', 'name': 'Animation'}] and rep['thumbnail'] == 'thumbnail.png'
	assert publish.check_report(rep, str(folder)) == []
	assert publish.default_title('timelapse', ARGS) == 'Animation of NDVI (Sentinel-2), annual frames, 2021-2023'


class _EE:
	"""An object of Earth Engine that only says how it was made (WHAT), for services.timelapse without it."""

	def __init__(self, what):
		self.what = what

	def __getattr__(self, name):
		return lambda *args, **kw: _EE(f"{self.what}.{name}({', '.join(map(repr, args))})")

	def __repr__(self):
		return self.what


@pytest.fixture
def offline(monkeypatch, tmp_path):
	"""services.timelapse without Earth Engine: what reaches the colour ramp (maps.vis_params, 'range') and the texts of
	the frames (animation.write, 'credits')."""
	from monitoreo import areas, composite, maps, variable
	seen = {}

	def vis_params(image, geom, entry=None, scale=None, vmin=None, vmax=None, palette=None, compute=True):
		seen['range'] = repr(image)
		return {'min': 0, 'max': 1, 'palette': ['000000', 'ffffff']}

	def write(pictures, path, labels, title, vmin, vmax, palette, unit='', credits='', fps=2):
		seen['credits'] = credits
		return path

	monkeypatch.setattr(animation, 'can_draw', lambda: None)
	monkeypatch.setattr(areas, 'region', lambda region: _EE('regions'))
	monkeypatch.setattr(services, '_bounds', lambda regions: seen.get('bounds', REGION['bbox']))
	monkeypatch.setattr(variable, 'image', lambda spec, geom, res: _EE('the map of the period'))
	monkeypatch.setattr(variable, 'collection', lambda spec, geom, res: _EE('images'))
	monkeypatch.setattr(composite, '_reduce', lambda col, metric: _EE(f'{metric} of {col!r}'))
	monkeypatch.setattr(animation, 'ee', types.SimpleNamespace(ImageCollection=types.SimpleNamespace(
		fromImages=lambda images: _EE(f'the collection {images!r}'))))
	monkeypatch.setattr(services, 'ee', types.SimpleNamespace(List=lambda xs: types.SimpleNamespace(
		getInfo=lambda: [1] * len(xs))))
	monkeypatch.setattr(maps, 'vis_params', vis_params)
	monkeypatch.setattr(animation, 'frames', lambda col, regions, steps, *a, **k: [None] * len(steps))
	monkeypatch.setattr(animation, 'fetch_frames', lambda frames, grid, progress=None: frames)
	monkeypatch.setattr(animation, 'write', write)
	monkeypatch.chdir(tmp_path)
	return seen


def test_the_colours_of_a_sum_or_a_count_are_those_of_a_frame(offline):
	"""The colours of every frame come from the map of the whole period, but those of a sum or a count, which grow with
	the images, from the median of the frames: the sum of 3 years of precipitation would be 3 times that of each frame,
	all of them painted with the first colour."""
	services.timelapse(REGION, 'PRECIP', 'TerraClimate', '2001-01-01', '2003-12-31', metric='sum')
	years = ', '.join(f"sum of images.filterDate('{y}-01-01', '{y + 1}-01-01')" for y in (2001, 2002, 2003))
	assert offline['range'] == f"the collection [{years}].median().rename('value').clipToCollection(regions)"
	services.timelapse(REGION, 'NDVI', 'Modis', '2001-01-01', '2003-12-31', step='monthly', metric='count')
	assert offline['range'].startswith("the collection [count of images.filterDate('2001-01-01', '2001-02-01'), ")
	assert offline['range'].count('count of images') == 36
	for metric in ('median', 'mean', 'p90', 'cv'):  # on the scale of a frame: the map of the whole period
		services.timelapse(REGION, 'NDVI', 'Modis', '2001-01-01', '2003-12-31', metric=metric)
		assert offline['range'] == 'the map of the period.clipToCollection(regions)', metric


def test_the_credits_of_the_region_are_written_on_the_frames(offline):
	"""The frames have the outline of the region: the credits of its data (FAO GAUL, Global Islands) are written on
	them, as they are in the result and the README."""
	region = {'admin1': 'Andalucía', 'country': 'Spain'}
	res = services.timelapse(region, 'NDVI', 'Modis', '2020-01-01', '2022-12-31')
	assert 'FAO GAUL' in offline['credits'] and all(c in offline['credits'] for c in res['credits'])
	services.timelapse({'island_at': [-16.5, 28.3]}, 'NDVI', 'Modis', '2020-01-01', '2022-12-31')
	assert 'CC BY-SA' in offline['credits']


def test_the_pixel_size_of_an_animation_is_that_of_its_frames(offline):
	"""Earth Engine computes the frames on their own pixels (web Mercator, DIMENSIONS on the longest side), not on those
	of the data when they are finer: the README says the size of those pixels, those of the data only when bigger."""
	offline['bounds'] = [-3.65, 36.9, -2.55, 37.25]  # 98 km wide: pixels of 163 m on the ground
	res = services.timelapse({'bbox': offline['bounds']}, 'NDVI', 'Sentinel-2', '2021-01-01', '2023-12-31')
	grid = animation.frame_grid(offline['bounds'], 600)
	assert (grid.width, grid.height) == (601, 241) and grid.res == pytest.approx(204.1, abs=0.1)
	assert res['scale'] == pytest.approx(162.8, abs=0.5)
	assert 'Pixel size of the computation: 162.8 m' in readme.text('timelapse', ARGS, res)
	assert animation.pixel_size(offline['bounds'], 1200, 10) == pytest.approx(res['scale'] / 2, rel=0.01)
	offline['bounds'] = REGION['bbox']  # 13 km: the pixels of MODIS (250 m) are bigger than those of the frames
	res = services.timelapse(REGION, 'NDVI', 'Modis', '2021-01-01', '2023-12-31')
	assert res['scale'] == 250


@pytest.fixture
def calls(monkeypatch):
	out = []

	def fake(region, variable=None, sensor=None, start=None, end=None, step='annual', metric='median', season=None,
	         quality=None, vmin=None, vmax=None, palette=None, dimensions=600, fps=2, path=None, progress=None,
	         **source):
		out.append(dict(source, region=region, variable=variable, sensor=sensor, start=start, end=end, step=step,
		                metric=metric, vmin=vmin, vmax=vmax, dimensions=dimensions, fps=fps, path=path))
		return dict(ANSWER, file=path, gif=path)
	monkeypatch.setattr(services, 'init', lambda project=None, shared=False, warn=True: 'p')
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)
	monkeypatch.setattr(services, 'timelapse', fake)
	return out


def test_the_command_line_makes_an_animation(calls, capsys):
	from monitoreo import cli
	cli.main(['timelapse', 'NDVI', '--sensor', 'Sentinel-2', '--region', json.dumps(REGION), '--start', '2021-01-01',
	          '--end', '2023-12-31', '--step', 'monthly', '--fps', '3', '--out', 'ndvi.mp4'])
	c = calls[-1]
	assert (c['step'], c['fps'], c['path'], c['metric']) == ('monthly', 3.0, 'ndvi.mp4', 'median')
	out = capsys.readouterr().out
	assert 'ndvi.mp4: NDVI Sentinel-2 | 3 frames, 2 per second | colours 0.1 to 0.8' in out
	assert 'monitoreo timelapse VARIABLE' in cli.__doc__


def test_the_mcp_server_makes_an_animation(calls, monkeypatch, tmp_path):
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	monkeypatch.setattr(mcp_server, 'OUTPUT', str(tmp_path))
	monkeypatch.setattr(mcp_server, '_ready', lambda: None)
	out = mcp_server.timelapse(REGION, 'NDVI', 'Sentinel-2', start='2021-01-01', end='2023-12-31', video=True)
	answer = json.loads(out[0])
	assert calls[-1]['path'].endswith('.mp4') and answer['n_frames'] == 3 and answer['frames'][1]['images'] == 0
	with pytest.raises(Exception, match='fixed layer'):
		mcp_server.timelapse(REGION, 'ELEVATION', 'Copernicus', start='2021-01-01', end='2023-12-31')
	assert 'timelapse' in mcp_server.INSTRUCTIONS


def test_a_video_animation_is_published_with_its_call(tmp_path):
	"""The GIF of an animation made as a video by the MCP server (its file is the MP4) finds its call in the log: the
	report has its title, frames, video, references and a call of Python that works (a path .mp4, not video)."""
	from monitoreo import publish
	PIL = pytest.importorskip('PIL.Image')
	out = tmp_path / 'mcp'
	out.mkdir()
	gif, mp4 = out / 'ndvi.gif', out / 'ndvi.mp4'
	frames = [PIL.new('RGB', (40, 30), c) for c in ('red', 'blue', 'green')]
	frames[0].save(gif, save_all=True, append_images=frames[1:], duration=500, loop=0)
	mp4.write_bytes(b'\x00\x00\x00\x18ftypmp42')
	args = dict(ARGS, video=True)
	publish.log_call('timelapse', args, dict(ANSWER, file=str(mp4), gif=str(gif)), str(out))
	log = publish.calls_log(str(out))
	assert publish._logged_call(str(gif), log)['tool'] == 'timelapse'
	assert publish._logged_call(str(mp4), log)['tool'] == 'timelapse'
	folder = tmp_path / 'report'
	folder.mkdir()
	rep = publish.build({'title': 'A video', 'summary': 'Frames', 'results': [str(gif)]}, 'a-video', str(out), [], log,
	                    str(folder))
	r = rep['results'][0]
	assert r['kind'] == 'animation' and r['title'] == 'Animation of NDVI (Sentinel-2), annual frames, 2021-2023'
	assert r['frames'] == ['2021', '2022', '2023'] and r['mp4'].endswith('.mp4') and r['call']['tool'] == 'timelapse'
	assert 'video' not in r['call']['python'] and 'path="animation.mp4"' in r['call']['python']
	cites = ' '.join(x['citation'] for x in rep['references'])
	assert 'Wu, Q. (2020)' in cites and 'Gorelick, N.' in cites and 'Tucker' in cites
	assert publish.check_report(rep, str(folder)) == []
	# its MP4 deleted (or moved): the GIF is published with its call, without the video
	mp4.unlink()
	folder = tmp_path / 'report2'
	folder.mkdir()
	rep = publish.build({'title': 'A video', 'summary': 'Frames', 'results': [str(gif)]}, 'a-video', str(out), [], log,
	                    str(folder))
	r = rep['results'][0]
	assert r['kind'] == 'animation' and r['call']['tool'] == 'timelapse' and r['frames'] == ['2021', '2022', '2023']
	assert 'mp4' not in r and not any(f.endswith('.mp4') for f in os.listdir(folder / 'files'))
	assert publish.check_report(rep, str(folder)) == []
	# the call of Python of a timelapse of the MCP server: services.timelapse has no video
	assert publish.python_call('timelapse', dict(ARGS, video=False)) == publish.python_call('timelapse', ARGS)
	call = publish.python_call('timelapse', ARGS)
	assert call.startswith('mo.timelapse(region=') and 'video' not in call and 'path' not in call


def test_the_assistant_shows_the_animation(tmp_path, monkeypatch):
	from monitoreo import assistant
	assert 'timelapse' in assistant.RESULTS and 'timelapse' in assistant.PROMPT
	monkeypatch.setattr(assistant, 'OUTPUT', str(tmp_path))
	gif = tmp_path / 'ndvi.gif'
	gif.write_bytes(b'GIF89a')
	a = assistant.Assistant.__new__(assistant.Assistant)
	a.layers, a.names = {}, {}
	card = a.card({'id': 1, 'title': 'Animation', 'image': 'data:image/png;base64,', 'tool': 'timelapse', 'args': ARGS,
	               'result': dict(ANSWER, file=str(gif), gif=str(gif))})
	assert card['image'] == '/files/ndvi.gif'  # the GIF, not its last frame
	assert [f['name'] for f in card['files']] == ['ndvi.gif']
	assert card['legend']['min'] == 0.1 and card['legend']['palette'] == ['ff0000', '00ff00']


APP = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
global.ee = new Proxy({}, {get: function () { return function () { return {}; }; }});  // nothing is computed
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[1], f), 'utf8'), {filename: f});
});
var mo = global.MonitorEO;
function attempt(f) {
	try { return f(); } catch (e) { return 'ERROR ' + e.message; }
}
process.stdout.write(JSON.stringify({
	labels: input.labels.map(function (l) { return mo.frameLabel(l[0], l[1], l[2], 'en'); }),
	steps: input.specs.map(function (s) { return attempt(function () { return mo.animationSteps(s[0], s[1]); }); })
}));
"""


def test_the_app_has_the_same_frames():
	"""The frames of the Earth Engine app (gee/core.js, in node): the same dates and steps as Python."""
	import shutil
	import subprocess
	from monitoreo import timeseries
	if not shutil.which('node'):
		pytest.skip('no node')
	labels = [('annual', '2021-01-01', '2022-01-01'), ('annual', '2021-10-01', '2022-06-01'),
	          ('monthly', '2021-05-01', '2021-06-01'), ('16-day', '2021-01-17', '2021-02-02')]
	specs = [({'period': ['2019-01-01', '2023-12-31'], 'season': None}, 'annual'),
	         ({'period': ['2020-01-01', '2021-12-31'], 'season': ['06-01', '08-31']}, 'monthly'),
	         ({'period': ['2021-01-01', '2021-03-31'], 'season': None}, '16-day'),
	         ({'period': ['2005-01-01', '2020-12-31'], 'season': None}, 'monthly'),
	         ({'period': ['2021-01-01', '2021-12-31'], 'season': None}, 'daily')]
	gee = os.path.join(os.path.dirname(__file__), '..', 'gee')
	run = subprocess.run(['node', '-e', APP, gee], input=json.dumps({'labels': labels, 'specs': specs}),
	                     capture_output=True, text=True, timeout=120)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout)
	assert out['labels'] == [animation.label(*x) for x in labels]
	for (spec, step), got in zip(specs[:3], out['steps']):
		assert got == [list(b) for b in timeseries.bins(spec, step)], step
	assert out['steps'][3].startswith('ERROR 192 frames: an animation has at most 120')
	assert out['steps'][4].startswith('ERROR unknown step daily')  # the days with images: only in Python


RANGE = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
function made(what) {  // an ee that computes nothing: each of its objects says how it was made
	return new Proxy(function () {}, {
		get: function (t, p) {
			if (p === 'what') return what;
			return typeof p === 'symbol' || p === 'then' || p === 'toJSON' ? undefined : made(what + '.' + p);
		},
		apply: function (t, self, args) { return made(what + '(' + args.map(shown).join(', ') + ')'); }
	});
}
function shown(a) {
	if (a && a.what) return a.what;
	if (Array.isArray(a)) return '[' + a.map(shown).join(', ') + ']';
	return typeof a === 'function' ? 'function' : JSON.stringify(a);
}
global.ee = made('ee');
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[1], f), 'utf8'), {filename: f});
});
var mo = global.MonitorEO;
process.stdout.write(JSON.stringify(input.map(function (x) {
	var s = mo.spec({ref: x[0], period: x[1], metric: x[2]});
	return mo.animationRange(s, made('regions'), mo.animationSteps(s, 'annual'), x[2]).what;
})));
"""


def test_the_app_colours_a_count_as_its_frames():
	"""The app (gee/core.js, in node) takes the colours of an animation of a count, as Python those of a sum or a count,
	from the median of its frames, and those of the other metrics from the map of the whole period."""
	import shutil
	import subprocess
	from monitoreo import catalog
	if not shutil.which('node'):
		pytest.skip('no node')
	ndvi, precip = catalog.find('NDVI', 'Modis')['ref'], catalog.find('PRECIP', 'TerraClimate')['ref']
	runs = [(ndvi, ['2001-01-01', '2003-12-31'], 'count'), (precip, ['2001-01-01', '2003-12-31'], 'sum'),
	        (ndvi, ['2001-01-01', '2003-12-31'], 'median')]
	gee = os.path.join(os.path.dirname(__file__), '..', 'gee')
	run = subprocess.run(['node', '-e', RANGE, gee], input=json.dumps(runs), capture_output=True, text=True,
	                     timeout=120)
	assert run.returncode == 0, run.stderr
	count, total, median = json.loads(run.stdout)
	for got, metric in ((count, 'count'), (total, 'sum')):
		assert got.startswith('ee.ImageCollection.fromImages(') and got.endswith(
			'.median().rename("value").clipToCollection(regions)'), metric
		assert all(f'.filterDate("{y}-01-01", "{y + 1}-01-01").reduce(ee.Reducer.{metric}())' in got
		           for y in (2001, 2002, 2003)), metric
	assert 'fromImages' not in median and median.endswith('.clipToCollection(regions)')
	assert 'ee.Reducer.median()' in median and '2001-01-01' in median and '2004-01-01' in median


def test_the_same_palette_with_and_without_pillow(tmp_path, monkeypatch):
	"""Pillow writes the GIF with the palette of write_gif: the grey of the pixels without data stays d9d9d9."""
	Image = pytest.importorskip('PIL.Image')
	frames = [np.full((30, 40, 3), 217, np.uint8), animation.annotate(np.full((60, 80, 3), 217, np.uint8), 0, ['2021'],
	                                                                   'title', 0, 1, ['0000ff', 'ff0000'])[:30, :40]]
	frames = [f[:30, :40] for f in frames]
	animation.save_gif(frames, str(tmp_path / 'pil.gif'), 500, animation.ramp(['0000ff', 'ff0000'], 200))
	gif = Image.open(tmp_path / 'pil.gif')
	assert tuple(np.asarray(gif.convert('RGB'))[5, 5]) == (217, 217, 217)


def test_a_clear_error_when_ffmpeg_fails(tmp_path, monkeypatch):
	monkeypatch.setattr(animation, '_ffmpegs', lambda: [])
	with pytest.raises(ValueError, match='needs ffmpeg'):
		animation.to_mp4('a.gif', 'a.mp4')
	monkeypatch.setattr(animation, '_ffmpegs', lambda: ['false'])  # a command that fails
	with pytest.raises(ValueError, match='ffmpeg could not make the MP4 video .*the GIF is a.gif'):
		animation.to_mp4('a.gif', 'a.mp4')
