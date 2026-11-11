"""Tests of the true colour (RGB) of the images of a variable (issue #24), without Earth Engine: which variables have
it, what is refused before computing, what is cited and how its GeoTIFF documents itself. The computation itself is
in tests/test_ee.py (pytest -m ee)."""

import json

import pytest

from monitoreo import catalog, composite, maps, publish, references, report, sensors, services, variable

REGION = {'bbox': [-3.62, 36.86, -3.50, 36.93]}
JUNE = {'start': '2021-06-01', 'end': '2021-06-30'}


def test_which_variables_have_true_colour():
	rgb = {(e['index'], e['sensor'], e['col']) for e in catalog.variables() if sensors.rgb_of(e)}
	sensors_of = {s for _, s, _ in rgb}
	assert sensors_of == {'Sentinel-2', 'Landsat', 'Modis'}
	assert {c for _, s, c in rgb if s == 'Modis'} == {'MODIS/061/MOD09GA', 'MODIS/061/MYD09GA'}  # the CF of MODIS
	assert ('NDVI', 'Sentinel-2', sensors.S2) in rgb and ('SCF', 'Landsat', 'LANDSAT') in rgb
	assert ('LST', 'Landsat', 'LANDSAT') in rgb  # the same scenes as its thermal band
	for index, sensor in [('NDVI', 'Modis'), ('LST', 'Modis'), ('ELEVATION', 'Copernicus'), ('PRECIP', 'TerraClimate'),
	                      ('PRECIP', 'ERA5-Land'), ('BIO01', 'WorldClim'), ('RBR', 'Sentinel-2'), ('RBR', 'Landsat')]:
		assert not services.has_rgb(index, sensor), (index, sensor)
	assert services.has_rgb('NDVI', 'Sentinel-2') and services.has_rgb('NBR', 'Landsat')
	assert services.has_rgb('CF', 'Modis', 'MODIS/061/MYD09GA') and not services.has_rgb('NOPE', 'Sentinel-2')
	rows = services.list_variables()
	assert sum(1 for r in rows if r.get('rgb')) == len(rgb)
	assert not any(r.get('rgb') for r in rows if r.get('static') or r.get('two_periods'))
	assert services.describe_variable('NDVI', 'Sentinel-2')['rgb'] is True
	assert services.describe_variable('NDVI', 'Modis')['rgb'] is False
	# the bands of each sensor are those of its red, green and blue surface reflectance, and give reflectance
	assert sensors.RGB['Sentinel-2'] == (['B4', 'B3', 'B2'], 0.0001, 0.0)
	assert sensors.RGB['Landsat'][0] == ['red', 'green', 'blue']  # renamed from SR_B3/B2/B1 and SR_B4/B3/B2
	assert sensors.LANDSAT_57['SR_B3'] == 'red' and sensors.LANDSAT_89['SR_B4'] == 'red'
	assert sensors.LANDSAT_57['SR_B1'] == 'blue' and sensors.LANDSAT_89['SR_B2'] == 'blue'
	assert sensors.RGB_BANDS == ['red', 'green', 'blue']


@pytest.mark.parametrize('kwargs, message', [
	({'variable': 'NDVI', 'sensor': 'Modis'}, 'has no true colour'),
	({'variable': 'LST', 'sensor': 'Modis'}, 'has no true colour'),
	({'variable': 'PRECIP', 'sensor': 'TerraClimate', 'metric': 'mean'}, 'has no true colour'),
	({'variable': 'ELEVATION', 'sensor': 'Copernicus', 'start': None, 'end': None}, 'fixed layer'),
	({'variable': 'RBR', 'sensor': 'Sentinel-2'}, 'burn_severity'),
	({'variable': 'NDVI', 'sensor': 'Sentinel-2', 'metric': 'sum'}, 'not a colour'),
	({'variable': 'NDVI', 'sensor': 'Sentinel-2', 'metric': 'std'}, 'not a colour'),
	({'variable': 'NDVI', 'sensor': 'Sentinel-2', 'metric': 'count'}, 'not a colour'),
	({'variable': 'NDVI', 'sensor': 'Sentinel-2', 'temporal': 'annual', 'interannual': 'std'}, 'not a colour'),
	({'variable': 'SCF', 'sensor': 'Landsat'}, "only takes the metric 'mean'"),  # its metric, as its map
	({'collection': 'IDAHO_EPSCOR/TERRACLIMATE', 'band': 'pr', 'metric': 'mean'}, 'only the variables of the catalog'),
])
@pytest.mark.parametrize('tool', ['rgb_map', 'download_rgb'])
def test_refused_before_earth_engine(tool, kwargs, message):
	"""What has no true colour is refused with a message, before any call to Earth Engine (none is initialised)."""
	args = dict(JUNE, **kwargs)
	with pytest.raises(ValueError, match=message):
		getattr(services, tool)(REGION, **args)


def test_metrics_of_the_true_colour():
	for m in ('mean', 'median', 'min', 'max', 'p50', 'p2.5', 'MEDIAN'):
		composite.check_rgb_metric(m)
	for m in ('sum', 'std', 'count', 'mode'):
		with pytest.raises(ValueError, match='not a colour'):
			composite.check_rgb_metric(m)
	with pytest.raises(ValueError, match='unknown metric'):
		composite.check_rgb_metric('p101')
	# max and min take the colours of one image (that of the highest or lowest value of the variable), the others
	# reduce each band; the variable alone (one band) is never a mosaic
	assert composite._mosaic('max', ('value', 'red', 'green', 'blue')) == 'max'
	assert composite._mosaic('MIN', ('value', 'red', 'green', 'blue')) == 'min'
	assert composite._mosaic('median', ('value', 'red', 'green', 'blue')) is None
	assert composite._mosaic('max', ('value',)) is None
	spec = services.make_spec('NDVI', 'Sentinel-2', **JUNE, metric='max', temporal='annual', interannual='min')
	variable.check_rgb(spec)
	scf = services.make_spec('SCF', 'Landsat', **JUNE, metric='mean')
	variable.check_rgb(scf)  # the true colour of the clear observations of the SCF


def test_the_record_of_its_geotiff():
	spec = services.make_spec('NDVI', 'Landsat', **JUNE, metric='median', quality={'snow': False})
	d = variable.describe(spec, rgb=True)
	assert d['true_colour']['bands'] == {'red': 'red', 'green': 'green', 'blue': 'blue'}
	assert (d['true_colour']['scale'], d['true_colour']['offset']) == (2.75e-05, -0.2)
	assert d['unit'] == catalog.RGB_UNIT and d['udunits'] == '1' and d['metric'] == 'median'
	assert d['pixel_filters']['snow'] is False and d['pixel_filters']['clouds'] is True  # those of the variable
	assert 'true_colour' not in variable.describe(spec)


def test_what_it_cites():
	"""The true colour cites the data and the pixel filters of the variable, but not the article of its formula
	(except for the algorithms that decide its pixels, the snow cover frequency and the cloud frequency, and for the
	metrics max and min, with which the variable chooses the image of each pixel)."""
	args = dict(JUNE, region=REGION, variable='NDVI', sensor='Sentinel-2')
	ndvi = {r['id'] for r in references.cite('map_layer', args)['references']}
	rgb = references.cite('rgb_map', args)
	ids = {r['id'] for r in rgb['references']}
	assert 'tucker1979' in ndvi and 'tucker1979' not in ids
	assert {'esa_s2_l2a', 'pasquarella2023', 'gorelick2017', 'monitoreo'} <= ids
	assert rgb['credits'] == ['Contains modified Copernicus Sentinel data 2021']
	assert {r['id'] for r in references.cite('download_rgb', args)['references']} == ids
	scf = dict(args, variable='SCF', sensor='Landsat', metric='mean')
	assert {r['id'] for r in references.cite('map_layer', scf)['references']} == \
		{r['id'] for r in references.cite('rgb_map', scf)['references']}
	assert {'rgb_map', 'download_rgb'} <= set(references.EARTH_ENGINE)
	# with max or min, the variable chooses the image of each pixel: its formula is cited
	top = {r['id'] for r in references.cite('rgb_map', dict(args, metric='max'))['references']}
	assert 'tucker1979' in top
	years = dict(args, metric='median', temporal='annual', interannual='MIN')
	assert 'tucker1979' in {r['id'] for r in references.cite('download_rgb', years)['references']}
	assert 'tucker1979' not in {r['id'] for r in references.cite('download_rgb', dict(years, temporal='period'))
	                            ['references']}  # without years, the metric between years does not apply


def test_stretch_without_earth_engine():
	"""Without computing (quick), the three bands are stretched over a fixed range of reflectance; a range given is
	kept."""
	assert maps.rgb_vis(None, None, compute=False) == {'bands': ['red', 'green', 'blue'], 'min': 0.0, 'max': 0.3}
	assert maps.rgb_vis(None, None, vmin=0.02, vmax=0.25) == {'bands': ['red', 'green', 'blue'], 'min': 0.02,
	                                                          'max': 0.25}
	assert maps.rgb_vis(None, None, vmin=0.1, vmax=0.1)['max'] > 0.1
	assert maps.RGB_STRETCH == (2, 98)


def test_its_geotiff_documents_itself(tmp_path):
	gdal = pytest.importorskip('osgeo.gdal')
	gdal.UseExceptions()
	path = str(tmp_path / 'NDVI_Sentinel-2_median_2021-06-01_2021-06-30_RGB.tif')

	def download_rgb(region, variable=None, sensor=None, start=None, end=None, metric='median', path=None, **source):
		ds = gdal.GetDriverByName('GTiff').Create(path, 4, 3, 3, gdal.GDT_Float32)
		ds.SetGeoTransform([450000, 10, 0, 4110000, 0, -10])
		ds.SetProjection('EPSG:32630')
		for i, b in enumerate(sensors.RGB_BANDS):
			ds.GetRasterBand(i + 1).SetDescription(b)
		ds = None
		return {'file': path, 'unit': catalog.RGB_UNIT, 'bands': list(sensors.RGB_BANDS), 'images': 6, 'min': 0.01,
		        'max': 0.31, 'resolution': 10, 'native_resolution': 10,
		        'grid': {'width': 4, 'height': 3, 'resolution': 10, 'crs': 'EPSG:32630'}}

	out = services._cited(download_rgb)(REGION, 'NDVI', 'Sentinel-2', path=path, **JUNE)
	ds = gdal.Open(path)
	assert [(ds.GetRasterBand(i).GetDescription(), ds.GetRasterBand(i).GetUnitType()) for i in (1, 2, 3)] == \
		[('red', '1'), ('green', '1'), ('blue', '1')]
	assert json.loads(ds.GetMetadata()['call'])['tool'] == 'download_rgb'
	ds = None
	text = ' '.join(open(out['readme'], encoding='utf-8').read().split())
	assert 'True colour of the images of NDVI (Sentinel-2), 1 Jun 2021 - 30 Jun 2021 (GeoTIFF)' in text
	assert '1 red: Surface reflectance, red (true colour) (1)' in text and '3 blue: Surface reflectance, blue' in text
	assert 'Colours: red, green and blue reflectance stretched from 0.01 to 0.31' in text
	assert 'on the same pixels as the variable' in text and 'Temporal metric: median' in text
	assert 'mo.download_rgb(' in text and 'Tucker' not in text


def test_report_and_viewer():
	args = dict(JUNE, region=REGION, variable='NDVI', sensor='Sentinel-2')
	assert report.item_title('rgb_map', args) == 'True colour of the images of NDVI (Sentinel-2), 1 Jun 2021 - 30 Jun 2021'
	facts = dict(report.item_facts('rgb_map', args, {'min': 0.02, 'max': 0.3, 'bands': ['red', 'green', 'blue']}))
	assert facts['Temporal metric'] == 'median' and facts['Bands'] == 'red, green, blue'
	assert 'stretched together' in facts['Method']
	assert publish.default_title('download_rgb', args).startswith('True colour of the images of NDVI')
	with pytest.raises(ValueError, match='cannot be published in the viewer'):
		publish._results({'tool': 'download_rgb', 'args': args, 'result': {'file': 'x.tif'}}, None, 0)


def test_the_viewer_refuses_a_true_colour_given_as_a_file(tmp_path):
	"""A GeoTIFF of the true colour made with Python, R or the command line and given to publish as a file (without
	its tool) is refused too, by its bands, instead of being shown as a ramp of its red band."""
	import os
	import types
	gdal = pytest.importorskip('osgeo.gdal')
	gdal.UseExceptions()
	path = str(tmp_path / 'colour.tif')
	ds = gdal.GetDriverByName('GTiff').Create(path, 4, 3, 3, gdal.GDT_Float32)
	ds.SetGeoTransform([450000, 10, 0, 4110000, 0, -10])
	ds.SetProjection('EPSG:32630')
	for i, b in enumerate(sensors.RGB_BANDS):
		ds.GetRasterBand(i + 1).SetDescription(b)
	ds = None
	files = types.SimpleNamespace(folder=str(tmp_path), add=lambda f, *a, **k: os.path.basename(f))
	with pytest.raises(ValueError, match='cannot be published in the viewer'):
		publish._results({'args': {}, 'result': {'file': path}}, files, 0)
