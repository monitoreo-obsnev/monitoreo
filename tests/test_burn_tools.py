"""The burn severity (services.burn_severity) in the tools that offer it: the command line (monitoreo burn), the MCP
server (its tool burn_severity: the names of its files and its answer) and the QGIS plugin (its help, the colours of
its layer, the same as in the assistant, and its place in the theme Fire), with the indices dNBR, RBR and RdNBR,
without Earth Engine and without QGIS. qgis/test_plugin.py runs the plugin with QGIS and Earth Engine."""

import json
import os
import re
import sys

import pytest

from monitoreo import catalog, fire, references, services, trends

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGION = {'bbox': [-5.23, 36.47, -5.10, 36.57]}  # the fire of Sierra Bermeja, September 2021
ARGS = ['--region', json.dumps(REGION), '--start', '2021-07-15', '--end', '2021-08-31', '--other-start', '2021-09-20',
        '--other-end', '2021-10-31']


def _read(*path):
	with open(os.path.join(ROOT, *path), encoding='utf-8') as f:
		return f.read()


@pytest.fixture
def burn(monkeypatch):
	"""services.burn_severity faked: the calls it gets, and an answer like that of Earth Engine."""
	calls = []

	def fake(region, sensor='Sentinel-2', start=None, end=None, other_start=None, other_end=None, metric='median',
	         *args, **kw):
		calls.append(dict(kw, region=region, sensor=sensor, start=start, end=end, other_start=other_start,
		                  other_end=other_end, metric=metric))
		title = f'Burn severity (dNBR, USGS) {sensor} ({metric}) | before {start} / {end}, after {other_start} / {other_end}'
		out = {'scale': 10.0, 'csv': kw.get('csv'), 'file': kw.get('path'), 'readme': '/tmp/fire.README.txt',
		       'resolution': 10.0, 'native_resolution': 10.0}
		out.update(references.cite('burn_severity', dict(kw, sensor=sensor, start=start, end=end)))  # as _cited
		if kw.get('perimeter'):  # the polygons of the burned area
			index = {'rbr': 'RBR', 'rdnbr': 'RdNBR'}.get(str(kw.get('index')).lower(), 'dNBR')
			out.update(perimeter=kw['perimeter'], perimeter_ha={'bbox': 2010.5}, perimeter_patches={'bbox': 3},
			           burned_min=fire.burned_min(index, kw.get('burned_min')),
			           min_ha=fire.PERIMETER_MIN_HA if kw.get('min_ha') is None else kw['min_ha'])
		if str(kw.get('index')).lower() == 'rdnbr':
			classes = fire.table([{'class': 1, 'sum': 600.25}, {'class': 3, 'sum': 1500.0}, {'class': 0, 'sum': 50.0}],
			                     'bbox', 'RdNBR')
			return dict(out, index='RdNBR', scale=500.0,
			            title=title.replace('(dNBR, USGS)', '(RdNBR, Miller & Thode 2007)'), classes=classes,
			            burned_ha={'bbox': 2100.25},
			            stats=[{'region': 'bbox', 'mean': 0.51234, 'median': 0.48, 'p10': 0.03, 'p90': 1.1, 'min': -0.4,
			                    'max': 1.9, 'ha': 2150.25}],
			            bands=['rdnbr', 'severity', 'dnbr', 'nbr_before', 'nbr_after'] if kw.get('path') else None)
		if str(kw.get('index')).upper() == 'RBR':
			return dict(out, index='RBR', title=title.replace('Burn severity (dNBR, USGS)', 'Relativized Burn Ratio (RBR)'),
			            stats=[{'region': 'bbox', 'mean': 0.31234, 'median': 0.29, 'p10': 0.02, 'p90': 0.6, 'min': -0.2,
			                    'max': 0.9, 'ha': 1234.56}], bands=['rbr', 'dnbr', 'nbr_before', 'nbr_after'])
		classes = fire.table([{'class': 1, 'sum': 600.25}, {'class': 4, 'sum': 1500.0}, {'class': 0, 'sum': 50.0}],
		                     'bbox')
		return dict(out, index='dNBR', title=title, classes=classes, burned_ha={'bbox': 2100.25},
		            bands=['dnbr', 'severity', 'nbr_before', 'nbr_after'])

	monkeypatch.setattr(services, 'init', lambda project=None, shared=False, warn=True: 'p')
	monkeypatch.setattr(services, 'eecu_warning', lambda **kw: None)
	monkeypatch.setattr(services, 'burn_severity', fake)
	return calls


def test_the_command_line_computes_the_burn_severity(burn, capsys, tmp_path):
	from monitoreo import cli
	csv, tif = str(tmp_path / 'fire.csv'), str(tmp_path / 'fire.tif')
	cli.main(['burn'] + ARGS + ['--csv', csv, '--out', tif])
	call = burn[-1]
	assert call['region'] == REGION and call['sensor'] == 'Sentinel-2' and call['metric'] == 'median'
	assert (call['start'], call['end'], call['other_start'], call['other_end']) == \
	       ('2021-07-15', '2021-08-31', '2021-09-20', '2021-10-31')
	assert call['index'] == 'dNBR' and call['csv'] == csv and call['path'] == tif and call['where'] is None
	out = capsys.readouterr().out
	lines = out.splitlines()
	assert lines[0].split() == ['region', 'class', 'label', 'dnbr_min', 'dnbr_max', 'ha']
	assert len([x for x in lines if x.startswith('bbox ')]) == len(fire.SEVERITY)  # every class, also those with 0 ha
	high = next(x for x in lines if 'High severity' in x).split()
	assert high[-2:] == ['0.66', '1500.0']  # its lowest dNBR, no highest one (not "None"), and its hectares
	assert 'None' not in out
	assert 'bbox: burned area (dNBR >= 0.1) 2100.2 ha' in out
	assert f'| CSV {csv} | GeoTIFF {tif} | README /tmp/fire.README.txt' in out
	assert out.rstrip().splitlines()[-1].startswith('Burn severity (dNBR, USGS) Sentinel-2 (median)')


def test_the_command_line_writes_the_perimeter(burn, capsys, tmp_path):
	"""monitoreo burn --perimeter: the polygons of the burned area, with the value from which a pixel is burned and
	the smallest patch, and their hectares."""
	from monitoreo import cli
	gpkg = str(tmp_path / 'fire.gpkg')
	cli.main(['burn'] + ARGS + ['--perimeter', gpkg, '--burned-min', '0.27', '--min-ha', '2'])
	call = burn[-1]
	assert (call['perimeter'], call['burned_min'], call['min_ha']) == (gpkg, 0.27, 2.0)
	out = capsys.readouterr().out
	assert 'bbox: perimeter of the burned area (dNBR >= 0.27, patches and islands of at least 2 ha) 2010.5 ha in 3 ' \
	       'patches' in out
	assert f'| perimeter {gpkg} |' in out
	cli.main(['burn'] + ARGS)  # as before: no perimeter unless asked for
	assert burn[-1]['perimeter'] is None and burn[-1]['burned_min'] is None and burn[-1]['min_ha'] is None
	assert 'perimeter' not in capsys.readouterr().out


@pytest.mark.parametrize('extra, error', [
	(['--min-ha', '2'], '--burned-min and --min-ha are for the perimeter'),
	(['--burned-min', '0.2'], '--burned-min and --min-ha are for the perimeter'),
	(['--index', 'RBR', '--perimeter', 'fire.gpkg'], '--index RBR has no classes: give --burned-min'),
])
def test_the_command_line_refuses_a_perimeter_without_what_it_needs(burn, capsys, extra, error):
	from monitoreo import cli
	with pytest.raises(SystemExit):
		cli.main(['burn'] + ARGS + extra)
	assert error in capsys.readouterr().err
	assert not burn


def test_the_command_line_computes_the_rbr(burn, capsys):
	from monitoreo import cli
	where = [{'variable': 'ELEVATION', 'sensor': 'Copernicus', 'min': 500}]
	cli.main(['burn'] + ARGS + ['--index', 'RBR', '--sensor', 'Landsat', '--resolution', '30', '--where',
	                            json.dumps(where)])
	call = burn[-1]
	assert call['index'] == 'RBR' and call['sensor'] == 'Landsat' and call['resolution'] == 30.0
	assert call['where'] == where and call['path'] is None and call['csv'] is None  # no files unless asked
	out = capsys.readouterr().out
	assert out.splitlines()[0].split() == ['region', 'mean', 'median', 'p10', 'p90', 'min', 'max', 'ha']
	assert out.splitlines()[1].split() == ['bbox', '0.3123', '0.29', '0.02', '0.6', '-0.2', '0.9', '1234.6']
	assert 'burned area' not in out and 'Relativized Burn Ratio (RBR) Landsat' in out


def test_the_command_line_refuses_wrong_arguments(burn, capsys):
	from monitoreo import cli
	with pytest.raises(SystemExit):
		cli.main(['burn'] + ARGS + ['--index', 'NDVI'])  # only dNBR, RBR or RdNBR
	with pytest.raises(SystemExit):
		cli.main(['burn'] + ARGS[:-2])  # without the period after the fire
	with pytest.raises(SystemExit, match='ERROR'):
		cli.main(['burn', '--region', '{"bbox": [0, 0,', *ARGS[2:]])  # a region that is not JSON: a message
	assert not burn
	assert 'monitoreo burn --sensor S --region JSON' in cli.__doc__


ONE_YEAR_AFTER = ['--other-start', '2022-07-15', '--other-end', '2022-08-31']  # the extended assessment of the RdNBR


def test_the_command_line_computes_the_rdnbr(burn, capsys, tmp_path):
	"""The RdNBR of Miller & Thode 2007 with MODIS Aqua: the hectares of each class of the article (every class, also
	those with 0 ha), the changed area (RdNBR >= 0.069, classes low to high: unchanged is not unburned) and the
	statistics of the RdNBR, as the RBR."""
	from monitoreo import cli
	csv, tif = str(tmp_path / 'rdnbr.csv'), str(tmp_path / 'rdnbr.tif')
	cli.main(['burn'] + ARGS[:6] + ONE_YEAR_AFTER + ['--index', 'RdNBR', '--sensor', 'Modis', '--collection',
	                                                 'MODIS/061/MYD09GA', '--csv', csv, '--out', tif])
	call = burn[-1]
	assert (call['index'], call['sensor'], call['collection']) == ('RdNBR', 'Modis', 'MODIS/061/MYD09GA')
	assert (call['other_start'], call['other_end'], call['csv'], call['path']) == ('2022-07-15', '2022-08-31', csv, tif)
	out = capsys.readouterr().out
	lines = out.splitlines()
	assert lines[0].split() == ['region', 'class', 'label', 'rdnbr_min', 'rdnbr_max', 'ha']
	rows = [x for x in lines if x.startswith('bbox ')]
	assert [r.split()[1] for r in rows[:len(fire.RDNBR_SEVERITY)]] == [str(c) for c, _, _ in fire.RDNBR_SEVERITY]
	assert rows[0].split()[2:] == ['Unchanged', '0.069', '50.0']  # no lowest RdNBR
	assert rows[1].split()[2:] == ['Low', 'severity', '0.069', '0.316', '600.2']
	assert rows[2].split()[-1] == '0.0'  # moderate: no hectares, still in the table
	assert rows[3].split()[2:] == ['High', 'severity', '0.641', '1500.0']  # no highest RdNBR
	assert 'None' not in out
	assert f'bbox: changed area (RdNBR >= {fire.RDNBR_BURNED:g}) 2100.2 ha' in out
	assert 'bbox: changed area (RdNBR >= 0.069) 2100.2 ha' in out and 'burned area' not in out
	stats = lines.index(next(x for x in lines if x.split()[:2] == ['region', 'mean']))
	assert lines[stats].split() == ['region', 'mean', 'median', 'p10', 'p90', 'min', 'max', 'ha']
	assert lines[stats + 1].split() == ['bbox', '0.5123', '0.48', '0.03', '1.1', '-0.4', '1.9', '2150.2']
	assert f'| CSV {csv} | GeoTIFF {tif} | README /tmp/fire.README.txt' in out
	assert lines[-1].startswith('Burn severity (RdNBR, Miller & Thode 2007) Modis (median) | before 2021-07-15')
	assert '| pixels of 500 m' in lines[-1]


def test_the_command_line_computes_the_rdnbr_of_sentinel2_and_landsat(burn, capsys):
	"""Without --collection: the default collection of each sensor (MODIS Terra for Modis)."""
	from monitoreo import cli
	for sensor in ('Sentinel-2', 'Landsat', 'Modis'):
		cli.main(['burn'] + ARGS + ['--index', 'RdNBR', '--sensor', sensor])
		call = burn[-1]
		assert (call['index'], call['sensor'], call['collection']) == ('RdNBR', sensor, None)
		assert call['path'] is None and call['csv'] is None  # no files unless asked
	assert 'changed area (RdNBR >= 0.069)' in capsys.readouterr().out


def test_the_command_line_refuses_modis_and_collection_without_rdnbr(burn, capsys):
	"""MODIS only with the RdNBR, and --collection only for the RdNBR of MODIS: refused before Earth Engine, with a
	message."""
	from monitoreo import cli
	for index in ('dNBR', 'RBR'):
		with pytest.raises(SystemExit):
			cli.main(['burn'] + ARGS + ['--index', index, '--sensor', 'Modis'])
		assert f'--sensor Modis is only for --index RdNBR: the {index} is computed with Sentinel-2 or Landsat' in \
		       capsys.readouterr().err
	for more in (['--index', 'RdNBR', '--sensor', 'Landsat'], ['--sensor', 'Sentinel-2'], []):
		with pytest.raises(SystemExit):
			cli.main(['burn'] + ARGS + more + ['--collection', 'MODIS/061/MYD09GA'])
		assert '--collection is only for --index RdNBR with --sensor Modis' in capsys.readouterr().err
	with pytest.raises(SystemExit):  # not a collection of the RdNBR of MODIS
		cli.main(['burn'] + ARGS + ['--index', 'RdNBR', '--sensor', 'Modis', '--collection', 'MODIS/061/MOD13Q1'])
	assert 'invalid choice' in capsys.readouterr().err
	assert not burn
	assert '[--index dNBR|RBR|RdNBR] [--collection ID]' in cli.__doc__


def test_the_help_of_the_command_line_explains_the_rdnbr(capsys, monkeypatch):
	from monitoreo import cli
	monkeypatch.setenv('COLUMNS', '1000')  # argparse does not cut the URLs or the words with hyphens
	with pytest.raises(SystemExit):
		cli.main(['burn', '--help'])
	text = ' '.join(capsys.readouterr().out.split())
	for words in ('{dNBR,RBR,RdNBR}', 'Miller & Thode 2007', '10.1016/j.rse.2006.12.006', 'sqrt(|NBR before|)',
	              'at least 0.001 (Howe et al. 2022)', 'without the factor 1000 of the article (0.641 here is 641 there)',
	              'without its offset', 'one year after the fire', 'unchanged is not unburned',
	              'only with --index RdNBR', 'MODIS/061/MYD09GA (Aqua', 'RdNBR: rdnbr, severity, dnbr, nbr_before and '
	              'nbr_after', 'hectares of each class (dNBR, RdNBR)'):
		assert words in text, words


# The MCP server -----------------------------------------------------------------------------------------------------

@pytest.fixture
def mcp(monkeypatch, tmp_path):
	"""The MCP server, writing to TMP_PATH, without connecting to Earth Engine."""
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	monkeypatch.setattr(mcp_server, 'OUTPUT', str(tmp_path))
	monkeypatch.setattr(mcp_server, '_ready', lambda: None)
	monkeypatch.setattr(services, 'eecu_warning', lambda *a, **k: None)
	return mcp_server


def test_the_mcp_server_computes_the_rdnbr(mcp, burn, tmp_path):
	"""The tool burn_severity with index RdNBR (in any case) and MODIS Aqua: its files are named after the index, and
	its answer has the classes, the changed area and the statistics of the RdNBR, with the README, the references
	(Miller & Thode 2007, Howe et al. 2022, Veraverbeke et al. 2010) and the credits."""
	answer = json.loads(mcp.burn_severity(REGION, '2021-07-15', '2021-08-31', '2022-07-15', '2022-08-31', sensor='Modis',
	                                      index='rdnbr', collection='MODIS/061/MYD09GA'))
	call = burn[-1]
	assert (call['index'], call['sensor'], call['collection']) == ('rdnbr', 'Modis', 'MODIS/061/MYD09GA')
	stem = r'burn_severity_RdNBR_Modis_2021-07-15_2021-08-31_2022-07-15_2022-08-31_\d{8}-\d{6}'
	for key, ext in (('path', 'tif'), ('csv', 'csv')):
		assert os.path.dirname(call[key]) == str(tmp_path)
		assert re.fullmatch(f'{stem}\\.{ext}', os.path.basename(call[key])), call[key]
	assert answer['index'] == 'RdNBR' and answer['burned_ha'] == {'bbox': 2100.25}
	assert [c['class'] for c in answer['classes']] == [c for c, _, _ in fire.RDNBR_SEVERITY]
	assert {'rdnbr_min', 'rdnbr_max'} <= set(answer['classes'][0]) and 'dnbr_min' not in answer['classes'][0]
	assert answer['stats'][0]['median'] == 0.48
	assert answer['bands'] == ['rdnbr', 'severity', 'dnbr', 'nbr_before', 'nbr_after']
	assert answer['readme'] == '/tmp/fire.README.txt' and isinstance(answer['credits'], list)  # MODIS asks for none
	assert {'miller2007', 'howe2022', 'veraverbeke2010'} <= {r['id'] for r in answer['references']}
	[logged] = [json.loads(x) for x in open(tmp_path / 'calls.jsonl', encoding='utf-8')]  # for publish_report
	assert logged['tool'] == 'burn_severity' and logged['args']['collection'] == 'MODIS/061/MYD09GA'


def test_the_mcp_server_names_the_files_of_each_burn_index(mcp, burn, tmp_path):
	"""The files of the dNBR keep their names, those of the RBR and the RdNBR say their index; collection reaches the
	services only when it is given."""
	names = {}
	for index in ('dNBR', 'RBR', 'RdNBR'):
		mcp.burn_severity(REGION, '2021-07-15', '2021-08-31', '2021-09-20', '2021-10-31', sensor='Landsat', index=index)
		names[index] = os.path.basename(burn[-1]['path'])
		assert burn[-1]['collection'] is None
	assert names['dNBR'].startswith('burn_severity_Landsat_2021-07-15_')
	assert names['RBR'].startswith('burn_severity_RBR_Landsat_2021-07-15_')
	assert names['RdNBR'].startswith('burn_severity_RdNBR_Landsat_2021-07-15_')


def test_the_mcp_server_writes_the_perimeter(mcp, burn, tmp_path):
	"""perimeter true: a GeoPackage next to the GeoTIFF, with its name and time, and its hectares in the answer;
	without it, nothing."""
	answer = json.loads(mcp.burn_severity(REGION, '2021-07-15', '2021-08-31', '2021-09-20', '2021-10-31',
	                                      index='RBR', perimeter=True, burned_min=0.1, min_ha=0.5))
	call = burn[-1]
	assert call['perimeter'] == call['path'][:-4] + '_perimeter.gpkg'
	assert os.path.dirname(call['perimeter']) == str(tmp_path)
	assert (call['burned_min'], call['min_ha']) == (0.1, 0.5)
	assert answer['perimeter'] == call['perimeter'] and answer['perimeter_ha'] == {'bbox': 2010.5}
	assert answer['burned_min'] == 0.1 and answer['min_ha'] == 0.5
	mcp.burn_severity(REGION, '2021-07-15', '2021-08-31', '2021-09-20', '2021-10-31')
	assert burn[-1]['perimeter'] is None and burn[-1]['burned_min'] is None
	doc = ' '.join(mcp.burn_severity.__doc__.split())
	for words in ('perimeter true', '{"file": <perimeter>, "name_field": "region"}', 'burned_min', 'min_ha',
	              'the RBR has no classes'):
		assert words in doc, words
	assert 'perimeter true' in ' '.join(mcp.INSTRUCTIONS.split())


def test_the_model_learns_the_rdnbr(mcp):
	import inspect
	doc = ' '.join(mcp.burn_severity.__doc__.split())
	for words in ('index "RdNBR"', 'Miller & Thode 2007', 'heterogeneous vegetation', 'to compare fires',
	              'unchanged < 0.069, low 0.069 to 0.316, moderate 0.316 to 0.641, high >= 0.641',
	              'without the factor 1000 of the article (0.641 here is 641 there)', 'without its offset',
	              '"Modis" (500 m, only with this index', 'collection "MODIS/061/MYD09GA"', 'one year after the fire',
	              'unchanged is not unburned', 'rdnbr, severity (class 0 to 3), dnbr, nbr_before and nbr_after'):
		assert words in doc, words
	params = inspect.signature(mcp.burn_severity).parameters
	assert params['collection'].default is None and params['index'].default == 'dNBR'
	text = ' '.join(mcp.INSTRUCTIONS.split())
	assert 'with index "RdNBR", the relative dNBR of Miller & Thode 2007 with the classes of the article' in text


@pytest.fixture
def helptexts(monkeypatch):
	"""The help of the QGIS plugin, which does not need QGIS."""
	monkeypatch.syspath_prepend(os.path.join(ROOT, 'qgis'))
	for name in [m for m in sys.modules if m.startswith('monitoreo_qgis')]:
		monkeypatch.delitem(sys.modules, name)
	import monitoreo_qgis.helptexts as module
	return module


def test_the_maps_of_the_burn_severity_have_the_same_colours_in_every_tool():
	"""fire.map_style draws the GeoTIFF of the burn severity in the QGIS plugin and in the assistant (report.map_style):
	the classes of the USGS of the band severity, or the band rbr with the reversed diverging ramp from -0.5 to 0.5."""
	from monitoreo import report
	style = fire.map_style(['dnbr', 'severity', 'nbr_before', 'nbr_after'])
	assert style['band'] == 2  # the band severity
	assert [c['value'] for c in style['classes']] == [c for c, _, _ in fire.SEVERITY]
	assert [c['color'] for c in style['classes']] == ['#' + fire.COLOURS[c] for c, _, _ in fire.SEVERITY]
	labels = [fire.class_label(c) for c in style['classes']]
	assert labels[0] == 'Enhanced regrowth, high (dNBR < -0.25)' and labels[2] == 'Unburned (dNBR -0.1 to 0.1)'
	assert labels[3] == 'Low severity (dNBR 0.1 to 0.27)' and labels[-1] == 'High severity (dNBR ≥ 0.66)'
	assert [report.class_label(c) for c in style['classes']] == labels
	rbr = fire.map_style(('rbr', 'dnbr', 'nbr_before', 'nbr_after'))
	assert rbr == {'band': 1, 'min': -0.5, 'max': 0.5, 'palette': list(reversed(trends.DIVERGING))}
	assert rbr['palette'][0] == trends.DIVERGING[-1] and (rbr['min'], rbr['max']) == fire.RBR_RANGE
	assert fire.map_style(['difference']) is None and fire.map_style(None) is None
	for bands, expected in ((['dnbr', 'severity', 'nbr_before', 'nbr_after'], style), (['rbr', 'dnbr'], rbr)):
		assert report.map_style('burn_severity', {}, {'bands': bands}) == expected  # the assistant, the same
	dock = _read('qgis', 'monitoreo_qgis', 'dock.py')
	assert "fire.map_style(res.get('bands'))" in dock and 'fire.class_label(c)' in dock  # and the QGIS plugin


def test_the_maps_of_the_rdnbr_have_the_classes_of_miller_and_thode():
	"""A GeoTIFF of the RdNBR (bands rdnbr, severity, dnbr, nbr_before, nbr_after) is drawn with the classes of Miller &
	Thode 2007 of its band severity (not those of the USGS, although it has a band dnbr), with the colours of the
	classes of the dNBR of the same name and their RdNBR in the legend; without its band severity, the band rdnbr
	with the reversed diverging ramp of the RBR, from -1.2 to 1.2."""
	from monitoreo import report
	bands = ['rdnbr', 'severity', 'dnbr', 'nbr_before', 'nbr_after']
	assert fire.index_of(bands) == 'RdNBR'
	style = fire.map_style(bands)
	assert style['band'] == 2  # the band severity
	assert [c['value'] for c in style['classes']] == [c for c, _, _ in fire.RDNBR_SEVERITY] == [0, 1, 2, 3]
	assert [c['color'] for c in style['classes']] == ['#' + fire.RDNBR_COLOURS[c] for c in range(4)]
	assert style['classes'] == fire.legend('RdNBR')
	labels = [fire.class_label(c) for c in style['classes']]
	assert labels == ['Unchanged (RdNBR < 0.069)', 'Low severity (RdNBR 0.069 to 0.316)',
	                  'Moderate severity (RdNBR 0.316 to 0.641)', 'High severity (RdNBR ≥ 0.641)']
	assert [report.class_label(c) for c in style['classes']] == labels
	assert report.map_style('burn_severity', {'index': 'RdNBR'}, {'bands': bands}) == style  # the assistant, the same
	# the colours of the classes of the dNBR with the same name: unburned, low, moderate-high and high severity
	assert [fire.RDNBR_COLOURS[c] for c in range(4)] == [fire.COLOURS[c] for c in (0, 1, 3, 4)]
	assert fire.legend()[0]['label'].startswith('Enhanced regrowth')  # the dNBR unchanged
	assert fire.limits(1, 'RdNBR') == (fire.RDNBR_BURNED, 0.316) and fire.limits(3, 'RdNBR') == (0.641, None)
	rdnbr = fire.map_style(['rdnbr', 'dnbr', 'nbr_before', 'nbr_after'])
	assert rdnbr == {'band': 1, 'min': -1.2, 'max': 1.2, 'palette': list(reversed(trends.DIVERGING))}
	assert (rdnbr['min'], rdnbr['max']) == fire.RDNBR_RANGE


def test_the_help_of_the_plugin_explains_the_burn_severity(helptexts):
	for key in ('fire_sensor', 'fire_index', 'fire_before', 'fire_after'):
		assert 'More in the manual' in helptexts.HELP[key], key
		assert f'{helptexts.about.MANUAL}/' in helptexts.HELP[key]
	text = helptexts.HELP['fire_index']
	for doi in ('10.3390/rs6031827', '10.3390/rs14133122'):  # Parks et al. 2014, Silva-Cardoza et al. 2022
		assert doi in text
	assert 'Key &amp; Benson' in text and 'QGIS-plugin#9-burn-severity-of-a-fire' in helptexts.HELP['fire_sensor']
	assert 'Burn severity of a fire' in helptexts.HELP['theme']


def test_the_help_of_the_plugin_explains_the_perimeter(helptexts):
	text = helptexts.HELP['fire_perimeter']
	for words in ('<b>Perimeter</b>', 'Region</b> → <b>Layer', 'dNBR ≥ 0.1', 'RdNBR ≥ 0.069', 'The RBR has no classes',
	              '1 ha', 'Save perimeter…', 'QGIS-plugin#9-burn-severity-of-a-fire'):
		assert words in text, words
	assert 'Save perimeter…' in helptexts.HELP['series_list']


def test_the_perimeter_is_in_every_tool():
	"""The perimeter of the burned area of burn_severity reaches every tool that computes the burn severity: the
	command line, the MCP server, the assistant, the QGIS plugin, the R package and the Earth Engine app (its port in
	core.js and its panel in ui.js, for the three indices, in the app that is published)."""
	cli, mcp = _read('src', 'monitoreo', 'cli.py'), _read('src', 'monitoreo', 'mcp_server.py')
	dock, r = _read('qgis', 'monitoreo_qgis', 'dock.py'), _read('r', 'monitoreo', 'R', 'monitoreo.R')
	core, ui, app = _read('gee', 'core.js'), _read('gee', 'ui.js'), _read('gee', 'monitoreo_app.js')
	assert 'perimeter=args.perimeter, burned_min=args.burned_min, min_ha=args.min_ha' in cli
	assert "perimeter=tif[:-4] + '_perimeter.gpkg' if perimeter else None" in mcp
	assert 'self.perimeter_args(index, stem)' in dock and 'self.add_perimeter_layer(res)' in dock
	assert 'perimeter = if (is.null(perimeter)) NULL else path.expand(perimeter)' in r
	assert 'function burnPerimeter(' in core and 'geometryInNativeProjection: true' in core
	for index, band in (('dNBR', 'dnbr'), ('RBR', 'rbr'), ('RdNBR', 'rdnbr')):
		assert f"perimeterWidget(out.image.select('{band}'), '{index}', scale, e, name, before, after)" in ui, index
	assert 'function perimeterWidget(' in app and 'function burnPerimeter(' in app  # built (gee/build.py)
	assert f'var PERIMETER_MIN_HA = {fire.PERIMETER_MIN_HA:g};' in core
	# the downloads of the app with their polygons: without .geo in the selectors, the GeoJSON had none
	fields = "var fields = ['region', 'ha', 'patches', 'index', 'burned_min', 'min_ha', 'sensor', 'before', 'after',\n\t\t\t\t\t'.geo'];"
	assert fields in ui and fields in app
	assert [f.strip(" '") for f in fields.split('[')[1].split(']')[0].replace('\n', '').replace('\t', '').split(',')] \
	       == fire.PERIMETER_FIELDS + ['.geo']  # the fields of the file of the package, and the polygons
	assert "index + ' ' + num(classes.burned)" not in ui  # the hint «dNBR 0.1», not «dNBR 0.1000»


def test_the_analyses_of_a_theme_are_in_every_tool():
	"""Each analysis of a theme of catalog.THEMES (burn_severity, of the fires) is offered by the command line, the QGIS
	plugin (only in its theme, as the Earth Engine app does), the R package and the Earth Engine app."""
	cli, dock = _read('src', 'monitoreo', 'cli.py'), _read('qgis', 'monitoreo_qgis', 'dock.py')
	r, app = _read('r', 'monitoreo', 'R', 'monitoreo.R'), _read('gee', 'ui.js')
	names = [n for t in catalog.THEMES for n in t.get('analyses') or []]
	assert names == ['burn_severity']
	for name in names:
		assert f'services.{name}(' in cli, f'the command line does not offer {name}'
		assert f'services.{name}(' in dock and f"self.theme_has('{name}')" in dock, f'the QGIS plugin and {name}'
		assert f'mo_{name} <- function' in r, f'the R package does not offer {name}'
		assert f"themeHas('{name}')" in app, f'the Earth Engine app does not offer {name}'
