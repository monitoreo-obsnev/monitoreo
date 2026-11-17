"""The municipalities of Spain as the administrative units of level 3 (monitoreo.municipalities), without Earth Engine:
the index of the package and its search (any case and accents), the region {"admin3": ...} checked offline, the
references and credit of the IGN, the command line, the MCP server and the assistant."""

import json

import pytest

from monitoreo import areas, cli, municipalities, references, services


def test_the_index_of_the_package():
	idx = municipalities.load()
	assert idx['source'] == municipalities.WFS and idx['asset'] == municipalities.ASSET and idx['date']
	codes = [r[0] for r in idx['rows']]
	assert codes == sorted(codes) and len(set(codes)) == len(codes)
	assert all(len(c) == 5 and c.isdigit() for c in codes)
	assert all(name and province and region for _, name, province, region in idx['rows'])
	assert ['18134', 'Monachil', 'Granada', 'Andalucía'] in idx['rows']


def test_a_municipality_by_its_name_in_any_case_and_accents_or_its_code():
	assert [u['ADMIN3_CODE'] for u in municipalities.find('MONACHIL')] == ['18134']
	found = municipalities.find('granada', limit=50)
	assert found[0] == {'ADMIN3_CODE': '18087', 'NAME': 'Granada', 'PROVINCE': 'Granada', 'REGION': 'Andalucía',
	                    'ISO3_CODE': 'ESP', 'DISP_EN': 'Granada (Granada)', 'level': 3}  # the very name first
	assert {'Alhama de Granada', 'Beas de Granada'} <= {u['NAME'] for u in found}
	assert [u['NAME'] for u in municipalities.find('18134')] == ['Monachil']
	assert all(u['PROVINCE'] == 'Granada' for u in municipalities.find('a', province='granada', limit=500))
	assert all(u['ADMIN3_CODE'].startswith('18') for u in municipalities.find('a', province='18', limit=500))
	assert municipalities._plain('Alacant/Alicante') == 'alacant alicante'
	assert municipalities._plain('Vitoria-Gasteiz') == 'vitoria gasteiz' and municipalities._plain('Lanjarón') == 'lanjaron'
	assert municipalities.name_of('18134') == 'Monachil' and municipalities.name_of('99999') is None


def test_the_codes_of_the_wfs():
	assert municipalities.is_municipality('34011818134')  # Monachil: 34, Andalucía 01, Granada 18, INE 18134
	assert not municipalities.is_municipality('34011800000')  # the province
	assert not municipalities.is_municipality('34020953001')  # a shared land (its INE part begins with 53)
	assert not municipalities.is_municipality('34205400001')  # a territory without a municipality (20)


def test_the_region_is_checked_without_earth_engine():
	assert areas.check({'admin3': '18134'}) == 'admin3'
	assert areas.municipality_codes(['18134', 18087]) == ['18134', '18087']
	with pytest.raises(ValueError, match="99999 is not one .*find_admin_units, level 3"):
		areas.check({'admin3': '99999'})
	assert areas.check({'wdpa_id': 389011, 'within': {'admin3': '18134'}}) == 'wdpa_id'


def test_find_admin_units_of_level_3_without_earth_engine():
	assert services.find_admin_units('monachil', 3)[0]['ADMIN3_CODE'] == '18134'
	assert services.find_admin_units('monachil', 3, 'esp')[0]['DISP_EN'] == 'Monachil (Granada)'
	with pytest.raises(ValueError, match='municipalities of Spain'):
		services.find_admin_units('Lisboa', 3, 'PRT')


def test_the_references_and_the_credit_of_the_ign():
	cited = references.cite('time_series', {'region': {'admin3': '18134'}, 'variable': 'NDVI', 'sensor': 'Landsat',
	                                        'start': '2020-01-01', 'end': '2020-12-31'})
	assert any('Instituto Geográfico Nacional' in r['text'] for r in cited['references'])
	assert municipalities.CREDIT in cited['credits'] and 'CC BY 4.0 ign.es' in municipalities.CREDIT


def test_the_command_line(capsys):
	cli.main(['units', 'monachil', '--level', '3'])
	out = capsys.readouterr().out
	assert '18134' in out and 'Monachil (Granada)' in out


def test_the_mcp_server_and_the_assistant():
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	found = json.loads(mcp_server.find_admin_units('monachil', level=3))
	assert found[0]['ADMIN3_CODE'] == '18134'
	from monitoreo import assistant
	assert assistant.unit_code(found[0]) == (3, '18134')
	assert '{"admin3": "18134"}: Monachil (Granada)' in assistant.units_text(found)
	assert 'municipalities of Spain' in assistant.units_text(found)
