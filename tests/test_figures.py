"""Figures of the maps for reports and papers (services.map_figure and monitoreo.figures), without Earth Engine: the
scale bar, the coordinates, the files (PNG, PDF and SVG from a synthetic map), the errors before Earth Engine, the
README, the report, the viewer of results, the command line and the MCP server. tests/test_ee.py makes one in Earth
Engine; qgis/test_analyses_offline.py, the print layout of the QGIS plugin."""

import ast
import inspect
import io
import json
import os

import pytest

from monitoreo import figures, publish, readme, references, report, services

REGION = {'bbox': [-3.62, 36.86, -3.50, 36.93]}
ARGS = {'region': REGION, 'variable': 'NDVI', 'sensor': 'Modis', 'start': '2023-06-01', 'end': '2023-08-31'}
MAP_FIGURE = inspect.signature(services.map_figure)  # of the real function (the tests fake it)


def test_the_scale_bar_and_the_coordinates():
	assert [figures.nice(x) for x in (0.7, 3, 7.9, 23, 480)] == [0.5, 2, 5, 20, 200]
	km, deg = figures.scale_bar([-3.6, 37.0, -2.6, 37.2])  # 1° of longitude at 37.1° N: 88.8 km
	assert km == 20 and abs(deg - 20 / (111.32 * 0.7972)) < 1e-3
	assert figures.degrees(-3.4, 'x') == '3.40° W' and figures.degrees(37.12, 'y') == '37.12° N'
	assert figures.padded([0, 0, 10, 10]) == pytest.approx([-0.4, -0.4, 10.4, 10.4])


def _drawn(monkeypatch, tmp_path, bounds, credits=('Contains modified Copernicus Sentinel data 2023',)):
	"""The figure (of matplotlib, drawn) of a synthetic map of BOUNDS (with their margin, as services.map_figure) with
	CREDITS."""
	pytest.importorskip('matplotlib')
	Image = pytest.importorskip('PIL.Image')
	from matplotlib.figure import Figure
	drawn, save = [], Figure.savefig
	monkeypatch.setattr(Figure, 'savefig', lambda self, *a, **kw: drawn.append(self) or save(self, *a, **kw))
	buf = io.BytesIO()
	Image.new('RGB', (200, 120), (90, 160, 60)).save(buf, 'PNG')
	vis = {'min': 0.1, 'max': 0.8, 'palette': ['ff0000', '00ff00']}
	figures.map_figure(buf.getvalue(), figures.padded(bounds), vis, 'NDVI', 'NDVI', list(credits),
	                   str(tmp_path / 'map.png'), dpi=100)
	return drawn[-1]


@pytest.mark.parametrize('bounds', [[-3.4056, 37.0955, -3.3944, 37.1045], [-3.41, 37.09, -3.39, 37.11],
                                    [-3.43, 37.08, -3.38, 37.12], [-3.6, 37.0, -2.6, 37.2]])
def test_the_labels_of_the_grid_tell_its_lines_apart(monkeypatch, tmp_path, bounds):
	# a region of 1, 2 or 5 km has lines every 0.0025°, 0.005° or 0.002°: their labels with the decimals of the step,
	# different and exact (not 3.40° W four times); a bigger one, with 2
	assert [figures.decimals(x) for x in (1, 0.1, 0.05, 0.005, 0.002, 0.0025)] == [2, 2, 2, 3, 3, 4]
	assert figures.decimals(2000, 0) == 0 and figures.degrees(-3.4025, 'x', 4) == '3.4025° W'
	ax = _drawn(monkeypatch, tmp_path, bounds).axes[0]
	for axis in (ax.xaxis, ax.yaxis):
		ticks, labels = axis.get_ticklocs(), [t.get_text() for t in axis.get_ticklabels()]
		assert len(set(labels)) == len(labels) == len(ticks), labels
		assert all(abs(float(t.split('°')[0]) - abs(v)) < 1e-9 for t, v in zip(labels, ticks)), (labels, ticks)
		if bounds[2] - bounds[0] > 0.5:
			assert all(len(t.split('°')[0].split('.')[1]) == 2 for t in labels), labels


@pytest.mark.parametrize('bounds', [[-3.62, 36.86, -3.50, 36.93], [-3.5, 36.0, -3.4, 38.0]])
def test_the_credits_have_their_room(monkeypatch, tmp_path, bounds):
	# five lines of credits (e.g. those of Sentinel-2, FAO GAUL and the citation of MonitorEO), under the colour ramp
	# and its unit, and under the map, also in a tall map: nothing over anything
	credits = ['Contains modified Copernicus Sentinel data 2023', 'Source: FAO GAUL 2025 (CC BY 4.0). The designations '
	           'employed and the presentation of material do not imply the expression of any opinion whatsoever on the '
	           'part of FAO concerning the legal status of any country, territory, city or area or of its authorities.',
	           'Line four', 'Computed with MonitorEO in Google Earth Engine. Observatorio de Cambio Global de Sierra '
	           'Nevada (2026). MonitorEO [Software]. Zenodo. https://doi.org/10.5281/zenodo.23814894']
	fig = _drawn(monkeypatch, tmp_path, bounds, credits)
	renderer = fig.canvas.get_renderer()
	text = next(t for t in fig.texts if t.get_text().startswith('Contains'))
	assert text.get_text().count('\n') + 1 >= 5
	box = text.get_window_extent(renderer)
	ramp, the_map = fig.axes[1].get_tightbbox(renderer), fig.axes[0].get_tightbbox(renderer)  # with labels and unit
	assert box.y1 < ramp.y0 and box.y1 < the_map.y0 and box.y0 >= 0, (box, ramp, the_map)


def test_the_north_arrow_of_a_very_wide_map(monkeypatch, tmp_path):
	# the north arrow has the same size on the page in a strip of 15:1 (a coast) as in any map, with the N above it,
	# readable, and both on the map
	sizes = []
	for bounds in ([-3.6, 37.0, -2.6, 37.2], [-10, 36, 5, 37]):
		fig = _drawn(monkeypatch, tmp_path, bounds)
		renderer, ax = fig.canvas.get_renderer(), fig.axes[0]
		n = next(t for t in ax.texts if t.get_text() == 'N').get_window_extent(renderer)
		arrow = next(t.arrow_patch for t in ax.texts if t.get_text() == '' and t.arrow_patch)
		arrow = arrow.get_window_extent(renderer)
		frame = ax.get_window_extent(renderer)
		assert n.y0 >= arrow.y1 - 1 and frame.y0 <= arrow.y0 and n.y1 <= frame.y1, (n, arrow, frame)
		sizes.append((round(arrow.height), round(arrow.width), round(n.height)))
	assert sizes[0] == sizes[1] and sizes[0][0] >= 20, sizes


def test_the_errors_before_earth_engine():
	for kwargs, text in (({'path': 'map.jpg'}, r'PNG \(\.png\), PDF'), ({'dpi': 1000}, 'from 72 to 600')):
		with pytest.raises(ValueError, match=text):
			services.map_figure(REGION, 'NDVI', 'Modis', '2023-06-01', '2023-08-31', **kwargs)


@pytest.mark.parametrize('ext', ['png', 'pdf', 'svg'])
def test_a_figure_of_a_synthetic_map(tmp_path, ext):
	pytest.importorskip('matplotlib')
	Image = pytest.importorskip('PIL.Image')
	buf = io.BytesIO()
	Image.new('RGB', (200, 120), (90, 160, 60)).save(buf, 'PNG')
	path = figures.map_figure(buf.getvalue(), [-3.62, 36.86, -3.50, 36.93], {'min': 0.1, 'max': 0.8,
	                                                                         'palette': ['ff0000', '00ff00']},
	                          'unit', 'NDVI', ['Contains modified Copernicus Sentinel data 2023', 'MonitorEO'],
	                          str(tmp_path / f'map.{ext}'), dpi=100)
	data = open(path, 'rb').read()
	assert data[:4] in (b'\x89PNG', b'%PDF') or b'<svg' in data[:500]
	if ext == 'svg':
		text = data.decode()
		assert '37.' in text or 'N' in text  # the labels of the latitudes are text


def test_the_readme_the_report_and_the_viewer_of_a_figure(tmp_path):
	from monitoreo import publish
	Image = pytest.importorskip('PIL.Image')
	png = tmp_path / 'figure.png'
	Image.new('RGB', (40, 30), 'white').save(png)
	result = {'file': str(png), 'min': 0.2, 'max': 0.7, 'unit': '[unitless]', 'name': 'NDVI Modis', 'scale': 250.0,
	          'dpi': 300}
	text = ' '.join(readme.text('map_figure', ARGS, result, computed='2026-11-14T10:00:00+01:00').split())
	assert 'figure.png: figure of the map (PNG), with its grid, scale bar, north arrow, colour ramp and credits' in text
	assert 'as the maps of cartoee of geemap' in text and 'mo.map_figure(region=' in text
	assert report.item_title('map_figure', ARGS).startswith('Figure of the map of NDVI (MODIS), ')
	assert 'wu2020' in [r['id'] for r in references.cite('map_figure', ARGS)['references']]
	spec = {'title': 'A figure', 'summary': 'A figure', 'region': {'name': 'Sierra Nevada'},
	        'results': [{'tool': 'map_figure', 'args': ARGS, 'result': result}]}
	folder = tmp_path / 'report'
	folder.mkdir()
	rep = publish.build(spec, 'a-figure', str(tmp_path), [], None, str(folder))
	r = rep['results'][0]
	assert r['kind'] == 'figure' and r['image'] == r['file'] and rep['thumbnail'] == 'thumbnail.png'
	assert publish.check_report(rep, str(folder)) == []


@pytest.fixture
def calls(monkeypatch):
	out = []

	def fake(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
	         interannual='mean', season=None, quality=None, vmin=None, vmax=None, palette=None, path=None, title=None,
	         dpi=300, width=7.0, dimensions=1600, **source):
		out.append({'variable': variable, 'path': path, 'title': title, 'dpi': dpi, 'vmin': vmin})
		with open(path, 'wb') as f:
			f.write(b'\x89PNG\r\n\x1a\n')
		return {'file': path, 'min': 0.2, 'max': 0.7, 'unit': '', 'name': 'NDVI Modis', 'dpi': dpi}
	monkeypatch.setattr(services, 'init', lambda project=None, shared=False, warn=True: 'p')
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)
	monkeypatch.setattr(services, 'map_figure', fake)
	return out


def test_the_command_line_and_the_mcp_server_make_a_figure(calls, monkeypatch, tmp_path, capsys):
	from monitoreo import cli
	out = str(tmp_path / 'ndvi.pdf')
	cli.main(['figure', 'NDVI', '--sensor', 'Modis', '--region', json.dumps(REGION), '--start', '2023-06-01', '--end',
	          '2023-08-31', '--out', out, '--dpi', '150', '--title', 'Summer NDVI'])
	assert calls[-1] == {'variable': 'NDVI', 'path': out, 'title': 'Summer NDVI', 'dpi': 150, 'vmin': None}
	assert 'ndvi.pdf: NDVI Modis | colours 0.2 to 0.7' in capsys.readouterr().out
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	monkeypatch.setattr(mcp_server, 'OUTPUT', str(tmp_path))
	monkeypatch.setattr(mcp_server, '_ready', lambda: None)
	res = mcp_server.map_layer(REGION, 'NDVI', 'Modis', '2023-06-01', '2023-08-31', figure=True)
	assert calls[-1]['path'].endswith('.png') and json.loads(res[0])['file'] == calls[-1]['path'] and len(res) == 2
	assert 'url' not in json.loads(res[0])  # the figure instead of the tiles, as its description says
	doc = ' '.join(mcp_server.map_layer.__doc__.split())
	assert 'figure: instead of the tiles, a figure' in doc and 'credits), in file.' in doc and 'figure_file' not in doc


def _call(text):
	"""The function and the arguments of the call TEXT of monitoreo.services (mo.f(k=v, ...)), as Python reads it."""
	call = ast.parse(text, mode='eval').body
	assert isinstance(call, ast.Call) and ast.unparse(call.func).startswith('mo.') and not call.args, text
	return ast.unparse(call.func)[3:], {k.arg: ast.literal_eval(k.value) for k in call.keywords}


def test_a_figure_of_the_mcp_server_and_the_assistant_published(calls, monkeypatch, tmp_path):
	# map_layer with figure (MCP server, assistant) is published as a figure, from its file (the log) or from its saved
	# answer, with the call of services.map_figure that makes it again; and a figure without its call, as a figure
	Image = pytest.importorskip('PIL.Image')
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	monkeypatch.setattr(mcp_server, 'OUTPUT', str(tmp_path))
	monkeypatch.setattr(mcp_server, '_ready', lambda: None)
	res = json.loads(mcp_server.map_layer(REGION, 'NDVI', 'Modis', '2023-06-01', '2023-08-31', figure=True)[0])
	Image.new('RGB', (40, 30), 'white').save(res['file'])
	logged = publish._logged_call(res['file'], publish.calls_log(str(tmp_path)))
	assert logged['tool'] == 'map_layer' and logged['args']['figure'] is True
	alone = tmp_path / 'other' / 'my_figure.png'
	alone.parent.mkdir()
	Image.new('RGB', (40, 30), 'white').save(alone)
	saved = {'call': {'tool': 'map_layer', 'args': dict(ARGS, figure=True, quick=False)}, 'text': [res]}
	spec = {'title': 'A figure', 'summary': 'A figure', 'region': {'name': 'Sierra Nevada'},
	        'results': [os.path.basename(res['file']), {'answer': saved}, str(alone)]}
	folder = tmp_path / 'report'
	folder.mkdir()
	rep = publish.build(spec, 'a-figure', str(tmp_path), [str(tmp_path)], publish.calls_log(str(tmp_path)), str(folder))
	assert [r['kind'] for r in rep['results']] == ['figure'] * 3 and publish.check_report(rep, str(folder)) == []
	for r in rep['results'][:2]:
		assert r['tool'] == 'map_figure' and r['title'] == 'Figure of the map of NDVI (MODIS), 1 Jun 2023 - 31 Aug 2023'
		name, kwargs = _call(r['call']['python'])
		assert name == 'map_figure' and 'figure' not in kwargs and 'quick' not in kwargs, kwargs
		MAP_FIGURE.bind(**kwargs)  # a call that services.map_figure takes
	assert rep['results'][2]['call'] is None and rep['results'][2]['image'] == rep['results'][2]['file']


def test_the_python_call_of_a_figure_of_map_layer():
	# the call of services that makes again the result of map_layer: with figure, that of map_figure (the MCP server and
	# the assistant), else that of map_layer; in the report of the assistant too
	for figure, name in ((True, 'map_figure'), (False, 'map_layer')):
		text = publish.python_call('map_layer', dict(ARGS, figure=figure, quick=True))
		got, kwargs = _call(text)
		assert got == name and 'figure' not in kwargs, text
		inspect.signature(getattr(services, name)).bind(**kwargs)
	assert _call(publish.python_call('map_layer', ARGS)) == ('map_layer', ARGS)
	html = report._item({'tool': 'map_layer', 'args': dict(ARGS, figure=True), 'result': {'file': 'figure.png'}}, 1,
	                    {}, [])
	assert 'mo.map_figure(region=' in html and 'figure=True' not in html
