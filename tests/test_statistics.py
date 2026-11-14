"""The statistics of any continuous variable of the catalog: the mean, the median, the minimum, the maximum, the
percentiles, the standard deviation and the coefficient of variation (cv: 100 × the standard deviation / the mean, in
%, Pearson 1896), as the metric of the images of each pixel, between the years and over the region (the statistic of
the time series, trends and comparisons, and the statistics of region_stats), in every tool. Without Earth Engine (a
fake ee) but the last tests, which compute in Earth Engine (pytest -m ee, with EE_PROJECT)."""

import json
import os
import shutil
import subprocess
import types

import pytest

from monitoreo import catalog, composite, references, services
from monitoreo import variable as variables

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEE = os.path.join(ROOT, 'gee')
REGION = {'bbox': [-3.62, 36.86, -3.50, 36.93]}
# the statistics that every continuous variable takes (as a metric, between the years and over the region)
STATISTICS = ['mean', 'median', 'min', 'max', 'std', 'cv', 'p5', 'p10', 'p25', 'p50', 'p75', 'p90', 'p95', 'p2.5']


def _dates(e):
	return (None, None) if e.get('static') else ('2021-01-01', '2022-12-31')


def test_every_statistic_is_a_metric():
	for m in STATISTICS + ['CV', ' Cv ', 'sum', 'count', 'mode']:
		composite.check_metric(m)
	for bad in ('cv2', 'variance', 'p101', 'coefficient'):
		with pytest.raises(ValueError, match='cv \\(coefficient of variation, %\\)'):
			composite.check_metric(bad)
	assert composite.is_cv('CV') and not composite.is_cv('std')
	assert set(composite.SPREAD) == {'std', 'cv'}


@pytest.mark.parametrize('e', [e for e in catalog.variables() if not e.get('two_periods')],
                         ids=lambda e: f"{e['index']}-{e['sensor']}-{e['ref']}")
def test_every_variable_of_the_catalog_takes_every_statistic(e):
	"""Every variable of the catalog (all of them are continuous) takes every statistic as the metric of its images,
	between the years and over the region; those with a single metric (the frequencies of snow and clouds, the mean of
	their images) take it between the years and over the region. The unit of a coefficient of variation is %."""
	start, end = _dates(e)
	for m in STATISTICS:
		metric = e.get('metric') or m  # the SCF and the CF: only the mean of their images
		spec = services.make_spec(e['index'], e['sensor'], start, end, metric=metric, temporal='annual',
		                          interannual=m, ref=e['ref'])
		assert services._unit(spec, 'cv') == '[%]'  # their coefficient of variation over the region
		if e.get('static'):  # a fixed layer: no metric of images, only the statistics of the region
			assert services._unit(spec) == e['unit']
			continue
		assert services._unit(spec) == ('[%]' if m == 'cv' else catalog.unit_of(e['unit'], metric))
		assert services._ylabel(spec, 'cv').startswith('Coefficient of variation [%]')
	if e.get('metric'):
		with pytest.raises(ValueError, match="only takes the metric 'mean'"):
			services.make_spec(e['index'], e['sensor'], *_dates(e), metric='cv', ref=e['ref'])


def test_the_unit_of_the_coefficient_of_variation():
	assert catalog.unit_of('[°C]', 'cv') == '[%]'
	assert catalog.unit_of('[mm/month]', 'sum', 'cv') == '[%]'  # the annual totals, then cv between the years
	assert catalog.unit_of('[mm/month]', 'sum', 'mean') == '[mm]'
	assert catalog.unit_of('[mm/month]', 'sum', None, 'cv') == '[%]'  # over the region
	assert catalog.unit_of('[mm/month]', 'sum', None, 'std') == '[mm]'
	assert catalog.unit_of('mm day-1', 'cv') == '%'  # the data of Earth Engine outside the catalog: in UDUNITS
	assert catalog.unit_of('', 'mean', None, 'cv') == '%'
	assert catalog.udunits(catalog.unit_of('[unitless]', 'cv')) == '%'
	spec = services.make_spec('NDVI', 'Modis', '2021-01-01', '2021-12-31', metric='mean', temporal='period',
	                          interannual='cv')
	assert services._unit(spec) == '[unitless]'  # the whole period: no metric between the years
	assert variables.describe(dict(spec, temporal='annual'))['udunits'] == '%'
	assert variables.describe(spec)['udunits'] == '1'


def test_the_coefficient_of_variation_of_numbers():
	assert composite.cv_number(2.5, 1.118) == pytest.approx(44.72)
	assert composite.cv_number(0, 1.0) is None  # no value where the mean is 0
	assert composite.cv_number(None, 1.0) is None and composite.cv_number(1.0, None) is None
	assert composite.cv_number(-2.0, 1.0) == -50.0  # σ / μ, as Pearson: negative with a negative mean


class _Reducer:
	"""A fake ee.Reducer: the names of its outputs, and those of the reducers it combines."""

	def __init__(self, *outputs):
		self.outputs = list(outputs)

	def combine(self, other, prefix='', shared=False):
		assert (prefix, shared) == ('', True)
		return _Reducer(*(self.outputs + other.outputs))

	def getOutputs(self):  # noqa: N802 (the names of Earth Engine)
		return types.SimpleNamespace(get=lambda i: self.outputs[i])


@pytest.fixture
def fake_ee(monkeypatch):
	def percentile(ps, *a):
		return _Reducer(*(f'p{p:g}' for p in ps))
	reducer = types.SimpleNamespace(mean=lambda: _Reducer('mean'), median=lambda: _Reducer('median'),
	                                min=lambda: _Reducer('min'), max=lambda: _Reducer('max'),
	                                stdDev=lambda: _Reducer('stdDev'), count=lambda: _Reducer('count'),
	                                sum=lambda: _Reducer('sum'), mode=lambda: _Reducer('mode'), percentile=percentile)
	monkeypatch.setattr(composite, 'ee', types.SimpleNamespace(
		Reducer=reducer, List=lambda xs: types.SimpleNamespace(getInfo=lambda: list(xs))))


def test_the_reducer_of_the_statistics_of_a_region(fake_ee):
	"""The coefficient of variation is computed from the mean and the standard deviation: each reducer once (Earth
	Engine refuses two outputs with the same name), whatever the statistics asked for."""
	red, names = composite.region_reducer(['mean', 'cv', 'p90', 'std', 'median'])
	assert red.outputs == ['count', 'mean', 'stdDev', 'p90', 'median']
	assert names == {'mean': 'mean', 'std': 'stdDev', 'p90': 'p90', 'median': 'median'}
	red, names = composite.region_reducer(['cv'])
	assert red.outputs == ['count', 'mean', 'stdDev']
	props = {'mean': 0.5, 'stdDev': 0.1, 'p90': 0.7, 'median': 0.45, 'count': 100}
	assert composite.value_of(props, 'cv', names) == pytest.approx(20.0)
	assert composite.value_of({'mean': 0, 'stdDev': 0.1}, 'CV', names) is None
	assert composite.value_of({}, 'cv', names) is None  # no pixels
	_, names = composite.region_reducer(['std', 'p90'])
	assert composite.value_of({'s0_stdDev': 0.1, 's0_p90': 0.7}, 'p90', names, 's0_') == 0.7


def test_the_default_statistics_of_region_stats():
	assert services.REGION_STATS == catalog.REGION_STATS
	assert 'cv' in services.REGION_STATS and 'std' in services.REGION_STATS


def test_the_colour_ramp_of_a_spread():
	"""The maps of a standard deviation or a coefficient of variation are not in the range of the variable: their
	colour ramp comes from the map (also with quick), and, if Earth Engine cannot compute it, 0 to 100 % for the
	coefficient of variation and 0 to half the range of the variable for the standard deviation."""
	ndvi = catalog.find('NDVI', 'Modis')
	spec = services.make_spec('NDVI', 'Modis', '2021-01-01', '2021-12-31', metric='cv')
	assert services.spread(spec) and services.ramp_entry(spec)['maxp'] == 100
	assert services.ramp_entry(spec)['pm'] == ndvi['pm']  # its palette
	spec = services.make_spec('NDVI', 'Modis', '2021-01-01', '2021-12-31', metric='std')
	assert services.ramp_entry(spec)['maxp'] == pytest.approx((ndvi['maxp'] - ndvi['minp']) / 2)
	spec = services.make_spec('NDVI', 'Modis', '2021-01-01', '2021-12-31', metric='mean', temporal='annual',
	                          interannual='cv')
	assert services.spread(spec) and services.ramp_entry(spec)['maxp'] == 100
	spec = services.make_spec('NDVI', 'Modis', '2021-01-01', '2021-12-31', metric='mean', interannual='cv')
	assert not services.spread(spec) and services.ramp_entry(spec) == services.variable_entry(spec)
	elevation = services.make_spec('ELEVATION', 'Copernicus', metric='cv', temporal='annual', interannual='cv')
	assert not services.spread(elevation)  # a fixed layer: no images, no metric


def test_the_true_colour_refuses_the_spreads():
	for m in ('std', 'cv'):
		with pytest.raises(ValueError, match=f'not {m}: the {m} of the red, green and blue bands is not a colour'):
			composite.check_rgb_metric(m)


def test_the_coefficient_of_variation_is_cited():
	"""Pearson (1896), who named it, with its DOI, when a result has coefficients of variation."""
	ref = references.bibliography()['pearson1896']
	assert ref['doi'] == '10.1098/rsta.1896.0007'
	base = {'region': REGION, 'variable': 'NDVI', 'sensor': 'Modis', 'start': '2021-01-01', 'end': '2021-12-31'}

	def ids(tool, **args):
		return [r['id'] for r in references.cite(tool, dict(base, **args))['references']]
	assert 'pearson1896' in ids('time_series', stat='cv')
	assert 'pearson1896' in ids('time_series', metric='cv')
	assert 'pearson1896' not in ids('time_series', stat='std')
	assert 'pearson1896' in ids('map_layer', temporal='annual', interannual='cv')
	assert 'pearson1896' not in ids('map_layer', temporal='period', interannual='cv')  # not used
	assert 'pearson1896' in ids('region_stats')  # its statistics by default have it
	assert 'pearson1896' not in ids('region_stats', stats=['mean', 'p90'])
	assert 'pearson1896' in ids('region_stats', stats='cv')
	assert 'pearson1896' in ids('burn_severity', index='RBR') and 'pearson1896' in ids('burn_severity', index='rdnbr')
	assert 'pearson1896' not in ids('burn_severity')  # the dNBR: its classes
	recipe = {'variables': [{'index': 'NDVI', 'sensor': 'Modis', 'metric': ['median', 'cv']}]}
	assert 'pearson1896' in ids('download_variables', recipe=recipe)
	recipe = {'variables': [{'index': 'NDVI', 'sensor': 'Modis', 'metric': 'median'}]}
	assert 'pearson1896' not in ids('download_variables', recipe=recipe)
	with open(os.path.join(ROOT, '.zenodo.json'), encoding='utf-8') as f:
		assert any('10.1098/rsta.1896.0007' in r for r in json.load(f)['references'])


def test_the_readme_describes_the_coefficient_of_variation(tmp_path):
	from monitoreo import readme
	assert '%' in readme.COLUMNS['cv'] and '{u}' not in readme.COLUMNS['cv']
	csv = tmp_path / 'series.csv'
	csv.write_text('region,date,value,n_pixels,n_images\nbbox,2021-01-01,23.5,100,3\n', encoding='utf-8')
	args = {'region': REGION, 'variable': 'NDVI', 'sensor': 'Modis', 'start': '2021-01-01', 'end': '2021-12-31',
	        'step': 'monthly', 'metric': 'mean', 'stat': 'cv'}
	result = {'rows': [], 'csv': str(csv), 'unit': '[%]', 'title': 'NDVI Modis'}
	text = readme.text('time_series', args, result, computed='2026-11-14T10:00:00+01:00')
	assert 'The values are coefficients of variation (100 × standard deviation / mean), in %' in text
	assert 'Pearson, K. (1896)' in text


# The tools ------------------------------------------------------------------------------------------------------------

@pytest.fixture
def stats_calls(monkeypatch):
	calls = []

	def fake(region, variable=None, sensor=None, start=None, end=None, metric='median', temporal='period',
	         interannual='mean', season=None, quality=None, stats=services.REGION_STATS, scale=None, **source):
		calls.append(dict(source, region=region, variable=variable, sensor=sensor, start=start, end=end, metric=metric,
		                  temporal=temporal, interannual=interannual, stats=stats, scale=scale))
		stats = list(stats or services.REGION_STATS)
		row = dict({s: 0.5 for s in stats}, region='bbox', n_pixels=120)
		row['cv'] = 18.25 if 'cv' in stats else None
		return {'rows': [row], 'stats': stats, 'scale': 250.0, 'unit': '[%]' if 'cv' in (metric, interannual) else
		        '[unitless]', 'title': f'{variable} {sensor} ({metric})'}
	monkeypatch.setattr(services, 'init', lambda project=None, shared=False, warn=True: 'p')
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)
	monkeypatch.setattr(services, 'region_stats', fake)
	return calls


def test_the_command_line_computes_the_statistics_of_a_region(stats_calls, capsys):
	from monitoreo import cli
	cli.main(['stats', 'PRECIP', '--sensor', 'TerraClimate', '--region', json.dumps(REGION), '--start', '2001-01-01',
	          '--end', '2020-12-31', '--metric', 'sum', '--temporal', 'annual', '--interannual', 'cv', '--stats',
	          'mean, cv,p90'])
	call = stats_calls[-1]
	assert (call['metric'], call['temporal'], call['interannual']) == ('sum', 'annual', 'cv')
	assert call['stats'] == ['mean', 'cv', 'p90']
	out = capsys.readouterr().out
	assert out.splitlines()[0].split() == ['region', 'mean', 'cv', 'p90', 'n_pixels']
	assert out.splitlines()[1].split() == ['bbox', '0.5', '18.25', '0.5', '120']
	assert '| unit [%] | cv in %' in out
	# a fixed layer, without dates, with the statistics by default
	cli.main(['stats', 'ELEVATION', '--sensor', 'Copernicus', '--region', json.dumps(REGION)])
	assert stats_calls[-1]['stats'] == list(services.REGION_STATS) and stats_calls[-1]['start'] is None
	assert 'monitoreo stats VARIABLE' in cli.__doc__


def test_the_command_line_explains_the_metrics(capsys):
	from monitoreo import cli
	for cmd in ('series', 'image', 'stats', 'trend', 'compare'):
		with pytest.raises(SystemExit):
			cli.main([cmd, '--help'])
		out = ' '.join(capsys.readouterr().out.split())
		assert 'cv (coefficient of variation' in out, cmd


def test_the_mcp_server_computes_the_statistics_of_a_region(stats_calls, monkeypatch, tmp_path):
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	monkeypatch.setattr(mcp_server, 'OUTPUT', str(tmp_path))
	monkeypatch.setattr(mcp_server, '_ready', lambda: None)
	answer = json.loads(mcp_server.region_stats(REGION, 'NDVI', 'Modis', '2021-01-01', '2021-12-31', metric='mean',
	                                            temporal='annual', interannual='cv', stats=['median', 'cv']))
	call = stats_calls[-1]
	assert (call['interannual'], call['stats']) == ('cv', ['median', 'cv'])
	assert answer['rows'][0]['cv'] == 18.25 and answer['unit'] == '[%]'
	mcp_server.region_stats(REGION, 'ELEVATION', 'Copernicus')
	assert stats_calls[-1]['stats'] is None  # those of services.region_stats
	assert 'cv (coefficient of variation' in ' '.join(mcp_server.INSTRUCTIONS.split())
	assert 'cv (coefficient of variation' in ' '.join(mcp_server.region_stats.__doc__.split())


def test_the_assistant_knows_the_statistics():
	from monitoreo import assistant
	prompt = assistant.system_prompt() if hasattr(assistant, 'system_prompt') else assistant.PROMPT
	text = ' '.join(prompt.split())
	assert 'cv (coefficient of variation: 100 × std / mean, in %)' in text
	assert 'interannual "cv"' in text


def test_the_qgis_plugin_offers_every_statistic():
	"""The lists of the plugin (read from its code: it imports QGIS): the metric of the images, between the years and
	over the region, with the standard deviation, the coefficient of variation and the percentiles; the statistics of
	the RBR and the RdNBR with them."""
	import ast
	with open(os.path.join(ROOT, 'qgis', 'monitoreo_qgis', 'dock.py'), encoding='utf-8') as f:
		dock = f.read()
	values = {}
	for node in ast.parse(dock).body:
		if isinstance(node, ast.Assign) and node.targets[0].id in ('PERCENTILES', 'SPREADS'):
			values[node.targets[0].id] = [v for _, v in ast.literal_eval(node.value)]
	assert values['SPREADS'] == ['std', 'cv']
	assert values['PERCENTILES'] == ['p5', 'p10', 'p25', 'p75', 'p90', 'p95']
	assert "STATS = [('Mean', 'mean'), ('Median', 'median'), ('Minimum', 'min'), ('Maximum', 'max')] + SPREADS + " \
		'PERCENTILES' in dock
	assert 'self.interannual = combo(METRICS, ' in dock
	with open(os.path.join(ROOT, 'qgis', 'monitoreo_qgis', 'results.py'), encoding='utf-8') as f:
		results = f.read()
	columns = next(ast.literal_eval(n.value) for n in ast.parse(results).body
	               if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'RBR_COLUMNS')
	assert [k for k, _ in columns] == services.RBR_COLUMNS


def test_the_reports_name_the_coefficient_of_variation():
	from monitoreo import report
	assert report._stat('cv') == 'coefficient of variation (%)'
	labels, body = report.item_table('region_stats', {'rows': [{'region': 'a', 'mean': 0.5, 'cv': 20.0},
	                                                           {'region': 'b', 'mean': 0.4, 'cv': 25.0}],
	                                                  'unit': '[unitless]'})
	assert labels == ['Region', 'Mean', 'CV (%)']


# The Earth Engine app (gee/core.js and gee/ui.js) ----------------------------------------------------------------------

NODE = r"""
var fs = require('fs'), path = require('path'), vm = require('vm');
global.ee = {};  // these functions do not call Earth Engine
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(process.argv[1], f), 'utf8'), {filename: f});
});
var mo = global.MonitorEO;
var input = JSON.parse(fs.readFileSync(0, 'utf8'));
var checks = input.metrics.map(function (m) {
	try { mo.checkMetric(m); return null; } catch (e) { return e.message; }
});
var units = input.units.map(function (u) { return mo.unitOf({unit: u[0]}, u[1], u[2], u[3]); });
var ndvi = mo.variables().filter(function (e) { return e.index === 'NDVI' && e.sensor === 'Modis'; })[0];
var ramps = input.ramps.map(function (r) {
	var e = mo.rampEntry(ndvi, r[0], r[1], r[2]);
	return [e.minp, e.maxp, mo.spread(r[0], r[1], r[2])];
});
var cvs = input.cvs.map(function (c) { return mo.cvNumber(c[0], c[1]); });
process.stdout.write(JSON.stringify({checks: checks, units: units, ramps: ramps, cvs: cvs, CV: mo.CV, SPREAD: mo.SPREAD}));
"""

UNITS = [['[°C]', 'cv', None, None], ['[mm/month]', 'sum', 'cv', None], ['[mm/month]', 'sum', 'mean', None],
         ['[mm/month]', 'sum', None, 'cv'], ['mm day-1', 'cv', None, None], ['[unitless]', 'std', None, 'p90']]
RAMPS = [['cv', 'period', 'mean'], ['std', 'period', 'mean'], ['mean', 'annual', 'cv'], ['mean', 'period', 'cv'],
         ['median', 'period', 'mean']]
CVS = [[2.5, 1.118], [0, 1], [None, 1], [-2, 1]]


@pytest.fixture(scope='module')
def app():
	if not shutil.which('node'):
		pytest.skip('no Node')
	metrics = STATISTICS + ['CV', 'sum', 'count', 'mode', 'cv2', 'variance']
	data = {'metrics': metrics, 'units': UNITS, 'ramps': RAMPS, 'cvs': CVS}
	run = subprocess.run(['node', '-e', NODE, GEE], input=json.dumps(data), capture_output=True, text=True, timeout=120)
	assert run.returncode == 0, run.stderr
	return dict(json.loads(run.stdout), metrics=metrics)


def test_the_app_takes_the_same_metrics(app):
	for m, js in zip(app['metrics'], app['checks']):
		try:
			composite.check_metric(m)
			python = None
		except ValueError as e:
			python = str(e)
		assert js == python, m
	assert app['CV'] == composite.CV and tuple(app['SPREAD']) == composite.SPREAD


def test_the_app_has_the_same_units_ramps_and_coefficients(app):
	assert app['units'] == [catalog.unit_of(*u) for u in UNITS]
	ndvi = catalog.find('NDVI', 'Modis')
	for (metric, temporal, interannual), js in zip(RAMPS, app['ramps']):
		spec = services.make_spec('NDVI', 'Modis', '2021-01-01', '2021-12-31', metric=metric, temporal=temporal,
		                          interannual=interannual)
		e = services.ramp_entry(spec)
		assert js == [e['minp'], e['maxp'], services.spread(spec)], (metric, temporal, interannual)
	assert app['ramps'][-1][:2] == [ndvi['minp'], ndvi['maxp']]
	assert app['cvs'] == [composite.cv_number(*c) for c in CVS]


def test_the_menus_of_the_app_have_every_statistic():
	from test_rgb_gee import _js_value, _read
	ui = _read('ui.js')
	for name in ('METRICS', 'STATS'):
		values = _js_value(ui, name)
		assert {'mean', 'median', 'min', 'max', 'std', 'cv', 'p5', 'p25', 'p75', 'p95'} <= set(values), name
	assert "cv: 'Coeficiente de variación (%)'" in ui and "cv: 'Coefficient of variation (%)'" in ui
	assert "var stats = ['mean', 'median', 'std', 'cv', 'p10', 'p90', 'min', 'max'];" in ui  # RBR and RdNBR
	with open(os.path.join(GEE, 'monitoreo_app.js'), encoding='ascii') as f:
		assert 'function rampEntry' in f.read()  # the script of the app, built again


# With Earth Engine ----------------------------------------------------------------------------------------------------

@pytest.mark.ee
@pytest.mark.skipif(not os.environ.get('EE_PROJECT'), reason='EE_PROJECT not set')
def test_the_coefficient_of_variation_of_images_and_of_a_region():
	"""Four images of 1, 2, 3 and 4 on every pixel: their coefficient of variation is 100 × σ / μ with the standard
	deviation of the population, 100 × 1.118 / 2.5 = 44.72 %; an image of 0 to 1 from west to east over a box, the
	coefficient of variation of its pixels; and a mean of 0, no value."""
	import ee
	import numpy as np
	services.init()
	col = ee.ImageCollection([ee.Image.constant(v).toFloat().rename('value') for v in (1, 2, 3, 4)])
	point = ee.Geometry.Point([-3.6, 36.9])
	value = composite._reduce(col, 'cv').reduceRegion(ee.Reducer.first(), point, 30).getInfo()['value']
	assert value == pytest.approx(100 * np.std([1, 2, 3, 4]) / 2.5, rel=1e-6)
	zero = ee.ImageCollection([ee.Image.constant(v).toFloat().rename('value') for v in (-1, 1)])
	assert composite._reduce(zero, 'cv').reduceRegion(ee.Reducer.first(), point, 30).getInfo()['value'] is None
	utm = ee.Projection('EPSG:32630')
	x0, y0, res, nx, ny = 300000, 4100000, 100, 50, 20
	i = ee.Image.pixelCoordinates(utm).select('x').subtract(x0).divide(res).floor()
	img = i.divide(nx - 1).rename('value')
	box = ee.Geometry.Rectangle([x0, y0, x0 + nx * res, y0 + ny * res], utm, False)
	red, names = composite.region_reducer(['mean', 'std', 'cv', 'p90'])
	props = img.reduceRegion(red, box, res, utm).getInfo()
	pixels = np.repeat(np.arange(nx) / (nx - 1), ny)
	assert composite.value_of(props, 'cv', names) == pytest.approx(100 * pixels.std() / pixels.mean(), rel=1e-3)
	assert composite.value_of(props, 'std', names) == pytest.approx(pixels.std(), rel=1e-3)
	feature = ee.Feature(None, props)
	server = composite.ee_value_of(feature, 'cv', None)
	assert ee.Number(server).getInfo() == pytest.approx(composite.value_of(props, 'cv', names), rel=1e-9)
