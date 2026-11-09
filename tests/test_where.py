"""Only the pixels of a study area that pass conditions on variables (where), without Earth Engine: the conditions,
their periods, their text in the READMEs and reports, their references and the argument in every tool."""

import inspect

import pytest

from monitoreo import cli, references, report, services, variable

ABOVE = {'variable': 'ELEVATION', 'sensor': 'Copernicus', 'min': 1500}
DRY = {'variable': 'PRECIP', 'sensor': 'TerraClimate', 'metric': 'sum', 'temporal': 'annual', 'max': 600}


def spec(*where, **kw):
	return services.make_spec('NDVI', 'Sentinel-2', kw.get('start', '2020-01-01'), kw.get('end', '2021-12-31'),
	                          where=list(where))


def test_conditions_over_the_period_of_the_result():
	(elev, lo, hi), (rain, lo2, hi2) = variable.where_specs(spec(ABOVE, DRY))
	assert (elev['index'], lo, hi) == ('ELEVATION', 1500, None)
	assert 'period' not in elev or not elev.get('period')  # a fixed layer has no period
	assert (rain['index'], rain['sensor'], rain['metric'], rain['temporal']) == ('PRECIP', 'TerraClimate', 'sum',
	                                                                             'annual')
	assert rain['period'] == ['2020-01-01', '2021-12-31'] and (lo2, hi2) == (None, 600)
	ndvi = variable.where_specs(spec({'variable': 'NDVI', 'sensor': 'Sentinel-2', 'min': 0.3}))[0][0]
	assert ndvi['metric'] == 'mean'  # by default, the mean of the period
	cf = variable.where_specs(spec({'variable': 'CF', 'sensor': 'Modis', 'max': 50}))[0][0]
	assert cf['metric'] == 'mean'  # the only metric of the cloud frequency


def test_a_condition_with_its_own_period():
	own = dict(DRY, period=['1991-01-01', '2020-12-31'])
	assert variable.where_specs(spec(own))[0][0]['period'] == ['1991-01-01', '2020-12-31']
	# a fixed layer (no period) filtered by a variable with dates: only with the period of the condition
	elevation = services.make_spec('ELEVATION', 'Copernicus', where=[own])
	assert variable.where_specs(elevation)[0][0]['period'] == ['1991-01-01', '2020-12-31']
	with pytest.raises(ValueError, match='needs a period'):
		variable.where_specs(services.make_spec('ELEVATION', 'Copernicus', where=[DRY]))
	assert variable.where_specs(services.make_spec('ELEVATION', 'Copernicus',
	                                               where=[{'variable': 'SLOPE', 'sensor': 'Copernicus', 'max': 20}]))


@pytest.mark.parametrize('condition, message', [
	({'variable': 'ELEVATION', 'sensor': 'Copernicus'}, 'min, max or both'),
	({'variable': 'ELEVATION', 'sensor': 'Copernicus', 'min': 1, 'above': 2}, 'unknown keys above'),
	({'sensor': 'Copernicus', 'min': 1}, 'dictionary with variable'),
	(dict(DRY, period='2020'), r'\[start, end\]'),
])
def test_wrong_conditions(condition, message):
	with pytest.raises(ValueError, match=message):
		variable.where_specs(spec(condition))


def test_two_periods_and_nested_conditions_are_refused():
	with pytest.raises((ValueError, KeyError)):
		variable.where_specs(spec({'variable': 'RBR', 'sensor': 'Sentinel-2', 'min': 0.1}))
	with pytest.raises(ValueError, match='unknown keys where'):
		variable.where_specs(spec(dict(ABOVE, where=[ABOVE])))


def test_the_same_pixels_in_both_periods_of_a_comparison():
	"""The conditions with dates of the other period of a comparison are those of the reference period."""
	source = services.same_area({'where': [ABOVE, DRY]}, '2018-01-01', '2018-12-31')
	assert source['where'][0] == dict(ABOVE, period=['2018-01-01', '2018-12-31'])  # unused by a fixed layer
	assert source['where'][1]['period'] == ['2018-01-01', '2018-12-31']
	own = dict(DRY, period=['1991-01-01', '2020-12-31'])
	assert variable.pin_where([own], '2018-01-01', '2018-12-31')[0]['period'] == ['1991-01-01', '2020-12-31']
	assert services.same_area({'collection': 'X'}, '2018-01-01', '2018-12-31') == {'collection': 'X'}


def test_text_and_facts():
	text = report.where_text([ABOVE, DRY])
	assert text == ('ELEVATION (Copernicus) ≥ 1,500 m; PRECIP (TerraClimate, sum of each year, mean between the '
	                'years) ≤ 600 mm')
	assert '2020-01-01 / 2020-12-31' in report.where_text([dict(DRY, period=['2020-01-01', '2020-12-31'])])
	facts = dict(report.item_facts('time_series', {
		'region': {'wdpa_id': 389011}, 'variable': 'NDVI', 'sensor': 'Modis', 'start': '2020-01-01',
		'end': '2020-12-31', 'where': [ABOVE]}, {'unit': '[-]'}))
	assert facts['Pixels of the region'] == 'only where ELEVATION (Copernicus) ≥ 1,500 m'


def test_references_of_the_conditions():
	cited = references.cite('time_series', {'region': {'wdpa_id': 389011}, 'variable': 'NDVI', 'sensor': 'Modis',
	                                        'start': '2020-01-01', 'end': '2020-12-31', 'where': [ABOVE, DRY]})
	text = ' '.join(r['text'] for r in cited['references'])
	assert 'Copernicus DEM' in text or 'GLO-30' in text
	assert 'TerraClimate' in text or 'Abatzoglou' in text


def test_every_tool_with_a_region_takes_where():
	from monitoreo import mcp_server
	tools = ['time_series', 'map_layer', 'region_stats', 'export_image_to_drive', 'export_time_series_to_drive',
	         'download_image', 'trend_table', 'trend_map', 'download_trend', 'compare_series', 'compare_map',
	         'download_comparison', 'burn_severity']
	for name in tools:
		fn = getattr(mcp_server, name)
		assert 'where' in inspect.signature(fn).parameters, name
		assert 'where: only the pixels' in fn.__doc__, name
	assert 'where' in inspect.signature(services.burn_severity).parameters
	assert 'every tool with a region takes where' in mcp_server.INSTRUCTIONS.lower()
	parser_help = cli.WHERE_HELP
	assert 'ELEVATION' in parser_help
