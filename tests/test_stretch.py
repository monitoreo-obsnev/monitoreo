"""The colour ramps of the maps stretched between the percentiles 1 and 99 of their own values (maps.STRETCH), or the
percentiles, minimum and maximum the user gives, in every tool, and said in their legends and READMEs, without Earth
Engine. The developer asked: «when we ask for a time series, the map of each time unit must use a colour palette with a
range fitted to its p1-99 values, and in general a colour palette must always be fitted to the p1-99 range, or the user
must be allowed to adjust these parameters»."""

import json
import types

import pytest

from monitoreo import maps, publish, readme, report, services


class Image:
	"""An image of Earth Engine faked: the reducer and arguments of its reduceRegion, and STATS as its answer."""
	def __init__(self, stats, seen):
		self.stats, self.seen = stats, seen

	def select(self, bands):
		return self

	def reduceRegion(self, reducer, *args, **kwargs):
		self.seen.append((reducer, kwargs))
		return self

	def getInfo(self):
		if isinstance(self.stats, Exception):
			raise self.stats
		return self.stats


@pytest.fixture
def fake_ee(monkeypatch):
	seen = []

	class List:
		def __init__(self, items):
			self.items = items

		def getInfo(self):
			return [i.getInfo() for i in self.items]

	fake = types.SimpleNamespace(Image=lambda img: img, List=List, EEException=RuntimeError,
	                             Reducer=types.SimpleNamespace(percentile=lambda ps, names=None: (tuple(ps), names)))
	monkeypatch.setattr(maps, 'ee', fake)
	return seen


def test_the_default_stretch_is_p1_p99():
	assert maps.STRETCH == (1, 99) and maps.RGB_STRETCH == (2, 98)
	assert maps.check_percentiles(None) == (1, 99) and maps.check_percentiles([]) == (1, 99)
	assert maps.check_percentiles('2, 98') == (2, 98) and maps.check_percentiles('2 98') == (2, 98)
	assert maps.check_percentiles([2.5, 97.5]) == (2.5, 97.5) and maps.check_percentiles(None, (2, 98)) == (2, 98)
	for wrong in ([99, 1], [1, 1], [-1, 50], [1, 101], [1], [1, 2, 3], 'a,b'):
		with pytest.raises(ValueError, match='percentiles'):
			maps.check_percentiles(wrong)


def test_a_map_is_stretched_between_its_percentiles(fake_ee):
	seen = fake_ee
	vis, how = maps.vis_params(Image({'value_lo': 0.12, 'value_hi': 0.81}, seen), 'region', None, 30, describe=True)
	assert (vis['min'], vis['max']) == (0.12, 0.81)
	assert seen[-1][0] == ((1, 99), ['lo', 'hi'])  # named, so that percentiles with decimals work too
	assert (seen[-1][1]['bestEffort'], seen[-1][1]['tileScale']) == (True, 4)
	assert how == {'method': 'percentiles', 'percentiles': [1, 99],
	               'text': 'stretched between the percentiles 1 and 99 of the values of the map over the region'}
	vis, how = maps.vis_params(Image({'value_lo': 0.2, 'value_hi': 0.7}, seen), 'region', percentiles=[5, 95],
	                           describe=True)
	assert seen[-1][0][0] == (5, 95) and how['percentiles'] == [5, 95]
	# the minimum given, the maximum from its percentile
	vis, how = maps.vis_params(Image({'value_lo': 0.2, 'value_hi': 0.7}, seen), 'region', vmin=0, describe=True)
	assert (vis['min'], vis['max']) == (0, 0.7) and how['method'] == 'mixed' and 'percentile 99' in how['text']
	# both given: no computation
	n = len(seen)
	vis, how = maps.vis_params(Image({}, seen), 'region', vmin=-1, vmax=1, describe=True)
	assert len(seen) == n and how['method'] == 'given'
	# Earth Engine cannot: the range of the catalog, said so
	vis, how = maps.vis_params(Image(RuntimeError('memory'), seen), 'region', {'minp': -0.2, 'maxp': 1},
	                           describe=True)
	assert (vis['min'], vis['max']) == (-0.2, 1) and how['method'] == 'catalog' and 'catalog' in how['text']


def test_each_step_has_its_own_range(fake_ee):
	images = [Image({'value_lo': 0.1, 'value_hi': 0.5}, fake_ee), Image({}, fake_ee),
	          Image({'value_lo': 0.3, 'value_hi': 0.9}, fake_ee)]
	assert maps.frame_ranges(images, 'region', 250) == [(0.1, 0.5), (None, None), (0.3, 0.9)]
	assert fake_ee[-1][0] == ((1, 99), ['lo', 'hi'])
	maps.frame_ranges(images, 'region', 250, [2, 98])
	assert fake_ee[-1][0][0] == (2, 98)


def test_the_true_colour_keeps_its_stretch_or_takes_the_percentiles_given(fake_ee):
	stats = {f'{b}_{k}': v for b in ('red', 'green', 'blue') for k, v in (('lo', 0.02), ('hi', 0.25))}
	vis, how = maps.rgb_vis(Image(stats, fake_ee), 'region', describe=True)
	assert fake_ee[-1][0][0] == (2, 98) and (vis['min'], vis['max']) == (0.02, 0.25)
	assert 'percentiles 2 and 98' in how['text']
	maps.rgb_vis(Image(stats, fake_ee), 'region', percentiles=[1, 99])
	assert fake_ee[-1][0][0] == (1, 99)


def test_the_readme_and_the_report_say_the_range_and_how():
	args = {'region': {'bbox': [-3.45, 37.02, -3.3, 37.12]}, 'variable': 'NDVI', 'sensor': 'Sentinel-2',
	        'start': '2021-01-01', 'end': '2021-12-31'}
	result = {'url': 'u', 'min': 0.12, 'max': 0.63, 'palette': ['ffffff', '00aa00'], 'unit': '[unitless]',
	          'stretch': maps.stretch_of(None, (1, 99), False, False), 'name': 'NDVI', 'bounds': [0, 0, 1, 1]}
	facts = dict(report.item_facts('map_layer', args, result))
	assert facts['Colours'] == '0.12 to 0.63: stretched between the percentiles 1 and 99 of the values of the map ' \
	                           'over the region'
	assert 'Colours: 0.12 to 0.63: stretched between the percentiles 1 and 99' in \
	       ' '.join(readme.text('map_layer', args, result).split())
	assert 'class="how"' in report._legend(result) and 'percentiles 1 and 99' in report._legend(result)
	given = dict(result, stretch=maps.stretch_of(None, (1, 99), True, True))
	assert dict(report.item_facts('map_layer', args, given))['Colours'].endswith('given by the user (vmin and vmax)')


def test_the_viewer_says_how_the_range_of_each_band_was_computed():
	import numpy as np
	args = {'variable': 'NDVI', 'sensor': 'Sentinel-2', 'start': '2021-01-01', 'end': '2021-12-31'}
	values = np.linspace(0, 1, 101, dtype='float32').reshape(1, -1)
	stretch = maps.stretch_of('the values of the file', (1, 99), False, False)
	[band] = publish._bands('download_image', args, {'min': 0.01, 'max': 0.99, 'stretch': stretch},
	                        {'value': values}, None, '[unitless]')
	assert band['legend']['how'] == 'stretched between the percentiles 1 and 99 of the values of the file'
	assert band['stats']['p_low'] == pytest.approx(0.01) and band['stats']['p_high'] == pytest.approx(0.99)
	bands = publish._bands('download_comparison', dict(args, other_start='2023-01-01', other_end='2023-12-31'), {},
	                       {'difference': values - 0.5, 'reference': values, 'other': values}, None, '[unitless]')
	how = {b['name']: b['legend'].get('how') for b in bands}
	assert how['difference'].startswith('symmetric around 0') and how['reference'].startswith('stretched between')


def test_the_command_line_takes_the_percentiles(monkeypatch, tmp_path, capsys):
	from monitoreo import cli
	calls = []

	def timelapse(region, **kw):
		calls.append(kw)
		return {'file': kw['path'], 'name': 'NDVI', 'n_frames': 2, 'fps': 1.0, 'min': 0.1, 'max': 0.9, 'unit': '',
		        'stretch': {'text': 'stretched between the percentiles 2 and 98 of the values of each frame'},
		        'frames': [{'label': '2021', 'images': 3, 'min': 0.1, 'max': 0.5},
		                   {'label': '2022', 'images': 2, 'min': 0.3, 'max': 0.9}]}

	def download_image(region, **kw):
		calls.append(kw)
		return {'file': kw['path'], 'grid': {'width': 6, 'height': 4}, 'resolution': 10.0, 'images': 3,
		        'name': 'NDVI', 'unit': '', 'min': 0.0, 'max': 0.8, 'stretch': maps.stretch_of(None, (1, 99), True,
		                                                                                         True)}

	monkeypatch.setattr(services, 'init', lambda project=None, shared=False, warn=True: 'p')
	monkeypatch.setattr(services, 'timelapse', timelapse)
	monkeypatch.setattr(services, 'download_image', download_image)
	region = json.dumps({'bbox': [-3.45, 37.02, -3.3, 37.12]})
	cli.main(['timelapse', 'NDVI', '--sensor', 'Modis', '--region', region, '--start', '2021-01-01', '--end',
	          '2022-12-31', '--out', str(tmp_path / 'a.gif'), '--percentiles', '2', '98'])
	assert calls[-1]['percentiles'] == [2, 98] and calls[-1]['same_colours'] is False
	out = capsys.readouterr().out
	assert '0.1 to 0.5' in out and '0.3 to 0.9' in out and 'percentiles 2 and 98 of the values of each frame' in out
	cli.main(['timelapse', 'NDVI', '--sensor', 'Modis', '--region', region, '--start', '2021-01-01', '--end',
	          '2022-12-31', '--out', str(tmp_path / 'a.gif'), '--same-colours'])
	assert calls[-1]['percentiles'] is None and calls[-1]['same_colours'] is True
	cli.main(['image', 'NDVI', '--sensor', 'Sentinel-2', '--region', region, '--start', '2021-01-01', '--end',
	          '2021-12-31', '--out', str(tmp_path / 'a.tif'), '--vmin', '0', '--vmax', '0.8'])
	assert (calls[-1]['vmin'], calls[-1]['vmax']) == (0, 0.8) and 'colours given 0 to 0.8' in capsys.readouterr().out


def test_the_colours_of_a_geotiff(tmp_path):
	"""The colours of a GeoTIFF (download_image, download_trend, download_comparison): between its percentiles, from the
	minimum and maximum given, or symmetric around 0 for a trend or a difference."""
	gdal = pytest.importorskip('osgeo.gdal')
	import numpy as np
	gdal.UseExceptions()
	path = str(tmp_path / 'values.tif')
	ds = gdal.GetDriverByName('GTiff').Create(path, 101, 1, 1, gdal.GDT_Float32)
	band = ds.GetRasterBand(1)
	band.SetNoDataValue(-9999)
	band.WriteArray(np.linspace(-0.2, 0.8, 101, dtype='float32').reshape(1, -1))
	ds = None
	colours, how = services._file_colours(path, (1, 99))
	assert colours['min'] == pytest.approx(-0.19, abs=1e-6) and colours['max'] == pytest.approx(0.79, abs=1e-6)
	assert how['text'] == 'stretched between the percentiles 1 and 99 of the values of the file'
	colours, how = services._file_colours(path, (1, 99), vmin=0)
	assert colours['min'] == 0 and colours['max'] == pytest.approx(0.79, abs=1e-6) and how['method'] == 'mixed'
	colours, how = services._file_colours(path, (1, 99), symmetric=True, over='the slope in the file')
	assert colours['min'] == pytest.approx(-0.79, abs=1e-6) and colours['max'] == pytest.approx(0.79, abs=1e-6)
	assert how['text'].startswith('symmetric around 0, up to the largest in absolute value of the percentiles 1 and 99')
	colours, how = services._file_colours(path, (1, 99), vmin=-1, vmax=1, symmetric=True)
	assert colours == {'min': -1.0, 'max': 1.0} and how['method'] == 'given'


def test_one_end_beyond_the_other_is_refused(fake_ee):
	"""A minimum given above the percentile 99 of the map (or a maximum below the percentile 1) would paint the ramp the
	other way round: a ValueError that says so; both ends given are kept as they are."""
	with pytest.raises(ValueError, match='minimum of the colours given, 0.9, is beyond'):
		maps.vis_params(Image({'value_lo': 0.1, 'value_hi': 0.8}, fake_ee), 'region', vmin=0.9)
	with pytest.raises(ValueError, match='maximum'):
		maps.vis_params(Image({'value_lo': 0.1, 'value_hi': 0.8}, fake_ee), 'region', vmax=0.05)
	assert maps.vis_params(None, None, vmin=0.5, vmax=0.5)['max'] > 0.5


def test_the_stretch_says_what_was_not_computed():
	every = maps.frame_stretch([(None, None)] * 3, (1, 99), False, False)
	assert every['method'] == 'catalog' and 'for every frame' in every['text']
	some = maps.frame_stretch([(0.1, 0.5), (None, None), (0.2, 0.6)], (1, 99), False, False)
	assert some['method'] == 'percentiles' and some['catalog_frames'] == [2] and 'frames 2 (without values)' in \
	       some['text']
	assert maps.frame_stretch([(0.1, 0.5)], (1, 99), True, True)['method'] == 'given'
	mixed = maps.stretch_of('the difference', (1, 99), True, False, symmetric=True)
	assert mixed['text'] == ('minimum given by the user, the other end symmetric around 0, up to the largest in '
	                         'absolute value of the percentiles 1 and 99 of the difference')
	assert maps.stretch_of(None, (1, 99), False, True, catalog=True)['text'].startswith(
		'maximum given by the user, the other end from the range of the variable in the catalog')
