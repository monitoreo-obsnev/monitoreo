"""The control ring of an affected area (monitoreo.control, services.control_ring and the option ring of time_series
and recovery_metrics), without Earth Engine: its options, the difference of the series, the command line, the
references and the facts of the README. The test marked ee builds it around the fire of Lanjarón (2005)."""

import os

import pytest

from monitoreo import cli, control, references, report, services


def test_the_options_of_the_ring():
	assert control.check(True) == control.DEFAULTS
	opts = control.check({'gap': '0', 'width': 800, 'match': 'slope'})
	assert (opts['gap'], opts['width'], opts['match']) == (0.0, 800.0, ['SLOPE'])
	assert control.check({'match': []})['match'] == []
	for bad, match in (({'width': 0}, 'width'), ({'gap': -1}, 'gap'), ({'size': 3}, 'unknown options size'),
	                   ({'match': ['NDVI']}, 'match takes'), ('yes', 'true, or the options'),
	                   ({'width': 'wide'}, 'distances in metres')):
		with pytest.raises(ValueError, match=match):
			control.check(bad)


def test_the_difference_of_the_series():
	rows = [{'region': 'affected', 'date': '2020-01-01', 'value': 0.3, 'n_images': 2},
	        {'region': 'control', 'date': '2020-01-01', 'value': 0.5},
	        {'region': 'affected', 'date': '2020-02-01', 'value': None},
	        {'region': 'control', 'date': '2020-02-01', 'value': 0.4},
	        {'region': 'affected', 'date': '2020-03-01', 'value': 0.6}]
	assert control.difference_rows(rows) == [{'region': 'affected - control', 'date': '2020-01-01', 'value': -0.2,
	                                          'n_pixels': None, 'n_images': 2}]


def test_the_ring_is_refused_with_what_it_cannot_take(monkeypatch):
	with pytest.raises(ValueError, match='not for the chart by day of the year'):
		services.time_series({'wdpa_id': 1}, 'NDVI', 'Landsat', '2014-01-01', '2016-12-31', doy=True, ring=True)
	with pytest.raises(ValueError, match='without affected and control'):
		services.recovery_metrics({'wdpa_id': 1}, 'NDVI', 'Landsat', '2014-01-01', '2020-12-31', event='2018-08-01',
		                          affected='burned', ring=True)
	with pytest.raises(ValueError, match='width'):
		services.time_series({'wdpa_id': 1}, 'NDVI', 'Landsat', '2014-01-01', '2016-12-31', ring={'width': -5})


def test_references_and_facts():
	args = {'region': {'wdpa_id': 1}, 'variable': 'NDVI', 'sensor': 'Landsat', 'start': '2014-01-01',
	        'end': '2016-12-31', 'ring': {'within': {'wdpa_id': 2}}}
	ids = [r['id'] for r in references.cite('time_series', args)['references']]
	assert 'copernicus_dem' in ids or any('dem' in i for i in ids), ids  # the elevation that matches the pixels
	facts = dict(report.item_facts('time_series', args, {'scale': 30, 'ring': {'gap': 150, 'width': 1500,
	                                                                          'match': {'ELEVATION': [1300, 2292]}}}))
	assert facts['Control ring'].startswith('from 150 to 1650 m of the affected area') and '1300 to 2292' in facts[
		'Control ring']
	ids = [r['id'] for r in references.cite('control_ring', {'region': {'wdpa_id': 1}, 'match': []})['references']]
	assert not any('dem' in i for i in ids)  # nothing matched: no elevation


def test_the_ring_command_runs(monkeypatch, capsys, tmp_path):
	"""monitoreo ring reaches the service with its options (it is not a command of a variable)."""
	got = {}

	def control_ring(region, gap, width, exclude, within, match, path=None):
		got.update(region=region, gap=gap, width=width, exclude=exclude, within=within, match=match, path=path)
		return {'ha': {'affected': 10.0, 'control': 20.0}, 'match': {'ELEVATION': [1000.0, 1500.0]},
		        'where': [{'variable': 'ELEVATION'}], 'file': path, 'title': 'Control ring'}
	monkeypatch.setattr(services, 'control_ring', control_ring)
	monkeypatch.setattr(services, 'init', lambda *a, **k: None)
	cli.main(['ring', '--region', '{"wdpa_id": 1}', '--out', str(tmp_path / 'z.gpkg'), '--gap', '0', '--match', 'SLOPE'])
	assert got['gap'] == 0 and got['width'] == 1500 and got['match'] == ['SLOPE'] and got['path'].endswith('z.gpkg')
	assert 'control: 20.0 ha' in capsys.readouterr().out


def test_where_as_one_condition_and_a_gap_of_0():
	assert services._where_list({'variable': 'ELEVATION', 'min': 1}) == [{'variable': 'ELEVATION', 'min': 1}]
	assert services._where_list(None) == []
	facts = dict(report.item_facts('control_ring', {'region': {'wdpa_id': 1}, 'gap': 0, 'width': 1000},
	                               {'gap': 0.0, 'width': 1000.0, 'match': {}}))
	assert facts['Control ring'].startswith('from 0 to 1000 m')
	ids = [r['id'] for r in references.cite('control_ring', {'region': {'wdpa_id': 1}, 'match': 'SLOPE',
	                                                         'within': {'country': 'ESP'}})['references']]
	assert any('dem' in i for i in ids) and len(ids) > 3  # the DEM of the slope, and the region of within
	assert services._polygons({'type': 'GeometryCollection', 'geometries': [
		{'type': 'Polygon', 'coordinates': [[[0, 0], [1, 0], [1, 1], [0, 0]]]}, {'type': 'LineString', 'coordinates': []}]}) == \
		{'type': 'MultiPolygon', 'coordinates': [[[[0, 0], [1, 0], [1, 1], [0, 0]]]]}


def test_the_command_line(capsys):
	with pytest.raises(SystemExit):
		cli.main(['ring', '--help'])
	text = ' '.join(capsys.readouterr().out.split())
	assert '--gap' in text and '--width' in text and '--exclude' in text and '--within' in text
	for cmd in ('series', 'recovery'):
		with pytest.raises(SystemExit):
			cli.main([cmd, '--help'])
		text = ' '.join(capsys.readouterr().out.split())
		assert '--ring ' in text and '--ring-width' in text, cmd
	import argparse
	assert cli._ring(argparse.Namespace(ring=True, ring_gap=None, ring_width=1000.0, ring_exclude=None,
	                                    ring_within='{"wdpa_id": 3}', ring_match=None)) == {'width': 1000.0,
	                                                                                        'within': {'wdpa_id': 3}}
	assert cli._ring(argparse.Namespace(ring=True, ring_gap=None, ring_width=None, ring_exclude=None,
	                                    ring_within=None, ring_match=None)) is True




@pytest.mark.ee
@pytest.mark.skipif(not os.environ.get('EE_PROJECT'), reason='EE_PROJECT not set')
def test_the_ring_of_the_fire_of_lanjaron(tmp_path):
	"""The ring around the burned area of Lanjarón (2005), from its perimeter burned with Landsat: some 5,000 ha, and
	the elevation of the burned area between about 1,000 and 2,300 m (the official perimeter, 1,300 to 2,292 m)."""
	services.init()
	fire = services.burn_severity({'bbox': [-3.60, 36.88, -3.36, 37.06]}, sensor='Landsat', start='2005-06-01',
	                              end='2005-09-15', other_start='2005-10-01', other_end='2005-11-30',
	                              perimeter=str(tmp_path / 'fire.gpkg'), largest=True)
	z = services.control_ring({'file': fire['perimeter'], 'name_field': 'region'}, path=str(tmp_path / 'zones.gpkg'))
	assert 3000 < z['ha']['affected'] < 4500 and z['ha']['control'] > 3000
	lo, hi = z['match']['ELEVATION']
	assert 900 < lo < 1500 and 2000 < hi < 2500 and os.path.exists(z["file"])  # the perimeter of Landsat reaches lower
	res = services.time_series({'file': fire['perimeter'], 'name_field': 'region'}, 'NDVI', 'Modis', '2004-01-01',
	                           '2007-12-31', step='annual', ring=True)
	regions = {r['region'] for r in res['rows']}
	assert regions == {'affected', 'control', 'affected - control'}
	after = [r['value'] for r in res['rows'] if r['region'] == 'affected - control' and r['date'] == '2006-01-01']
	assert after and after[0] < -0.05  # the burned area below its control the year after the fire
