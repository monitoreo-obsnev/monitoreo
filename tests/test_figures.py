"""Figures of the maps for reports and papers (services.map_figure and monitoreo.figures), without Earth Engine: the
scale bar, the coordinates, the files (PNG, PDF and SVG from a synthetic map), the errors before Earth Engine, the
README, the report, the viewer of results, the command line and the MCP server. tests/test_ee.py makes one in Earth
Engine; qgis/test_analyses_offline.py, the print layout of the QGIS plugin."""

import io
import json
import os

import pytest

from monitoreo import figures, readme, references, report, services

REGION = {'bbox': [-3.62, 36.86, -3.50, 36.93]}
ARGS = {'region': REGION, 'variable': 'NDVI', 'sensor': 'Modis', 'start': '2023-06-01', 'end': '2023-08-31'}


def test_the_scale_bar_and_the_coordinates():
	assert [figures.nice(x) for x in (0.7, 3, 7.9, 23, 480)] == [0.5, 2, 5, 20, 200]
	km, deg = figures.scale_bar([-3.6, 37.0, -2.6, 37.2])  # 1° of longitude at 37.1° N: 88.8 km
	assert km == 20 and abs(deg - 20 / (111.32 * 0.7972)) < 1e-3
	assert figures.degrees(-3.4, 'x') == '3.40° W' and figures.degrees(37.12, 'y') == '37.12° N'
	assert figures.padded([0, 0, 10, 10]) == pytest.approx([-0.4, -0.4, 10.4, 10.4])


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
	assert 'figure' in ' '.join(mcp_server.map_layer.__doc__.split())
