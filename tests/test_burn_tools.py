"""The burn severity (services.burn_severity) in the tools that offer it besides the MCP server: the command line
(monitoreo burn) and the QGIS plugin (its help, the colours of its layer and its place in the theme Fire), without
Earth Engine and without QGIS. qgis/test_plugin.py runs the plugin with QGIS and Earth Engine."""

import json
import os
import sys

import pytest

from monitoreo import catalog, fire, services, trends

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
		cli.main(['burn'] + ARGS + ['--index', 'NDVI'])  # only dNBR or RBR
	with pytest.raises(SystemExit):
		cli.main(['burn'] + ARGS[:-2])  # without the period after the fire
	with pytest.raises(SystemExit, match='ERROR'):
		cli.main(['burn', '--region', '{"bbox": [0, 0,', *ARGS[2:]])  # a region that is not JSON: a message
	assert not burn
	assert 'monitoreo burn --sensor S --region JSON' in cli.__doc__


@pytest.fixture
def plugin(monkeypatch):
	"""The modules of the QGIS plugin that do not need QGIS (helptexts, styles)."""
	monkeypatch.syspath_prepend(os.path.join(ROOT, 'qgis'))
	for name in [m for m in sys.modules if m.startswith('monitoreo_qgis')]:
		monkeypatch.delitem(sys.modules, name)
	import monitoreo_qgis.helptexts as helptexts
	import monitoreo_qgis.styles as styles
	return helptexts, styles


def test_the_layer_of_the_plugin_has_the_colours_of_the_other_tools(plugin):
	_, styles = plugin
	style = styles.burn_style({'bands': ['dnbr', 'severity', 'nbr_before', 'nbr_after']})
	assert style['band'] == 2  # the band severity
	assert [c['value'] for c in style['classes']] == [c for c, _, _ in fire.SEVERITY]
	assert [c['color'] for c in style['classes']] == ['#' + fire.COLOURS[c] for c, _, _ in fire.SEVERITY]
	labels = [c['label'] for c in style['classes']]
	assert labels[0] == 'Enhanced regrowth, high (dNBR < -0.25)'
	assert labels[3] == 'Low severity (dNBR 0.1 to 0.27)' and labels[-1] == 'High severity (dNBR ≥ 0.66)'
	rbr = styles.burn_style({'bands': ['rbr', 'dnbr', 'nbr_before', 'nbr_after']})
	assert rbr == {'band': 1, 'min': -0.5, 'max': 0.5, 'palette': list(reversed(trends.DIVERGING))}
	assert rbr['palette'][0] == trends.DIVERGING[-1] and (rbr['min'], rbr['max']) == fire.RBR_RANGE
	assert styles.burn_style({'bands': ['difference']}) is None and styles.burn_style({}) is None


def test_the_help_of_the_plugin_explains_the_burn_severity(plugin):
	helptexts, _ = plugin
	for key in ('fire_sensor', 'fire_index', 'fire_before', 'fire_after'):
		assert 'More in the manual' in helptexts.HELP[key], key
		assert f'{helptexts.about.MANUAL}/' in helptexts.HELP[key]
	text = helptexts.HELP['fire_index']
	for doi in ('10.3390/rs6031827', '10.3390/rs14133122'):  # Parks et al. 2014, Silva-Cardoza et al. 2022
		assert doi in text
	assert 'Key &amp; Benson' in text and 'QGIS-plugin#9-burn-severity-of-a-fire' in helptexts.HELP['fire_sensor']
	assert 'Burn severity of a fire' in helptexts.HELP['theme']


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
