"""The municipalities of Spain as the administrative units of level 3 (monitoreo.municipalities), without Earth Engine:
the index of the package and its search (any case and accents, the apostrophes typed in any way), the region
{"admin3": ...} checked offline and named in the READMEs, reports and titles, the references and credit of the IGN, the
command line (which does not connect to Earth Engine for them), the MCP server and the assistant (its list of units,
on the page too)."""

import asyncio
import json
import os
import shutil
import subprocess

import pytest

from monitoreo import areas, cli, municipalities, readme, references, report, services

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def test_the_apostrophes_typed_in_any_way():
	"""The apostrophe of the Catalan names typed as iOS and macOS write it (’), pasted (‘, ʼ) or with the acute accent
	of the Spanish keyboards (´) is that of the index ('): the names were not found, as the letters after it were
	joined to those before ('lhospitalet')."""
	for apostrophe in "'\u2019\u2018\u02bc\u00b4":
		assert municipalities._plain(f'L{apostrophe}Hospitalet') == "l'hospitalet", repr(apostrophe)
		assert municipalities.find(f'L{apostrophe}Hospitalet')[0]['ADMIN3_CODE'] == '08101'
		assert [u['ADMIN3_CODE'] for u in municipalities.find(f'Sant Joan d{apostrophe}Alacant')] == ['03119']
		assert municipalities.find(f"L{apostrophe}ALFÀS DEL PI")[0]['NAME'] == "l'Alfàs del Pi"
	assert municipalities._plain("Vandellòs i l\u2019Hospitalet de l\u2019Infant") == "vandellos i l'hospitalet de l'infant"
	assert services.find_admin_units('L\u2019Hospitalet de Llobregat', 3)[0]['DISP_EN'] == "L'Hospitalet de Llobregat (Barcelona)"


def test_the_region_is_named_in_the_readmes_reports_and_titles():
	"""{"admin3": CODE} as 'name (province), municipality of Spain (IGN)': with the name that the assistant found, or
	that of the index of the package (the README of a result of any tool); it was the dict itself."""
	assert report.region_text({'admin3': '18134'}) == 'Monachil (Granada), municipality of Spain (IGN)'
	assert report.region_text({'admin3': [18134, '4001']}) == ('Monachil (Granada), municipality of Spain (IGN); '
	                                                           'Abla (Almería), municipality of Spain (IGN)')
	assert report.region_text({'admin3': '99999'}) == 'Municipality 99999 of Spain (IGN)'
	names = {'admin3:08019': 'Barcelona (Barcelona)'}
	assert report.region_text({'admin3': '08019'}, names) == 'Barcelona (Barcelona), municipality of Spain (IGN)'
	assert report.region_text({'wdpa_id': 1, 'within': {'admin3': '08019'}}) == (
		'Protected area WDPA 1 within Barcelona (Barcelona), municipality of Spain (IGN)')
	assert municipalities.label('18134') == municipalities.label(18134) == 'Monachil (Granada)'
	assert municipalities.label(4001) == 'Abla (Almería)' and municipalities.label('99999') is None
	args = {'region': {'admin3': '18134'}, 'variable': 'NDVI', 'sensor': 'Modis', 'start': '2020-01-01',
	        'end': '2020-12-31'}
	assert report.item_facts('time_series', args, None)[0] == ('Region', 'Monachil (Granada), municipality of Spain (IGN)')
	text = readme.text('time_series', args, {'unit': '[unitless]'})
	assert 'Monachil (Granada), municipality of Spain (IGN)' in text and "{'admin3'" not in text


def test_the_command_line_without_earth_engine(capsys, monkeypatch):
	"""monitoreo units TEXT --level 3 answers from the index of the package: it connected to Earth Engine first, and
	failed without credentials, network or EECUs."""
	def refused(*args, **kw):
		raise AssertionError('Earth Engine used')
	monkeypatch.setattr(services, 'init', refused)
	monkeypatch.setattr(services, 'eecu_warning', refused)
	cli.main(['units', 'monachil', '--level', '3'])
	out = capsys.readouterr().out
	assert '18134' in out and 'Monachil (Granada)' in out
	with pytest.raises(AssertionError, match='Earth Engine used'):  # levels 1 and 2 are searched in Earth Engine
		cli.main(['units', 'Granada', '--level', '2'])
	assert 'units TEXT [--level 1|2|3]' in cli.__doc__


def test_the_mcp_server_and_the_assistant():
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	found = json.loads(mcp_server.find_admin_units('monachil', level=3))
	assert found[0]['ADMIN3_CODE'] == '18134'
	from monitoreo import assistant
	assert assistant.unit_code(found[0]) == (3, '18134')
	assert '{"admin3": "18134"}: Monachil (Granada)' in assistant.units_text(found)
	assert 'municipalities of Spain' in assistant.units_text(found)


def _assistant_with_units():
	assistant = pytest.importorskip('monitoreo.assistant')

	class Units(assistant.Assistant):
		"""An assistant whose MCP server finds the municipalities as find_admin_units of level 3."""

		async def call(self, name, args):
			return None, [json.dumps(services.find_admin_units(args['text'], args.get('level', 1)))], []

	a = Units({**assistant.DEFAULTS, 'project': 'p'})
	schema = {'type': 'object', 'properties': {'text': {'type': 'string'}, 'level': {'type': 'integer'}}}
	a.tools = assistant.model_tools([{'name': 'find_admin_units', 'description': 'Units.', 'inputSchema': schema}])
	a.messages.append({'role': 'user', 'content': 'NDVI del municipio'})
	return assistant, a


def _run(a, call):
	async def run():
		return [e async for e in a.run_tool(call)]
	return asyncio.run(run())


def test_the_assistant_goes_on_with_the_very_name(monkeypatch):
	"""A municipality whose very name is unique among those found (Granada, with Alhama de Granada, Beas de Granada...)
	is computed at once, as with FAO GAUL; with two of that name (Castejón, of Cuenca and of Navarra), the user
	chooses. The level 3 has NAME, not GAUL3_NAME: the user always had to choose."""
	assistant, a = _assistant_with_units()
	monkeypatch.setattr(assistant, 'signed_in', lambda: True)
	found = municipalities.find('Granada')
	assert len(found) > 1 and not assistant.units_must_choose(found, 'Granada')
	assert not assistant.units_must_choose(found, ' granada ')
	assert assistant.units_must_choose(found, 'Gran')  # no very name: the user chooses
	castejon = municipalities.find('Castejón')
	assert [u['NAME'] for u in castejon[:2]] == ['Castejón', 'Castejón']
	assert assistant.units_must_choose(castejon, 'Castejón')
	assert not assistant.units_must_choose(castejon, 'Castejón', 'Compute it with ... admin3 31070')
	events = _run(a, {'name': 'find_admin_units', 'arguments': {'text': 'Granada', 'level': 3}})
	assert [e['type'] for e in events if e['type'] != 'status'] == ['units'] and not a.waiting
	assert a.names['admin3:18087'] == 'Granada (Granada)'
	args = {'region': {'admin3': '18087'}, 'variable': 'NDVI', 'sensor': 'Sentinel-2', 'start': '2021-01-01',
	        'end': '2021-12-31'}
	assert a.titled('time_series', args).endswith(' · Granada (Granada), municipality of Spain (IGN)')
	_run(a, {'name': 'find_admin_units', 'arguments': {'text': 'Castejón', 'level': 3}})
	assert a.waiting and a.names['admin3:31070'] == 'Castejón (Navarra)'


# unitsCard of ui/assistant.html in Node, with a DOM that draws nothing: the buttons of the units found and what each
# one sends
CARD = r"""
class Elem {
  constructor(tag, attrs = {}) { this.tag = tag; this.children = []; this.text = attrs.text || ''; }
  append(...c) { this.children.push(...c); }
  querySelectorAll() { return []; }
}
function el(tag, attrs = {}, ...children) { const e = new Elem(tag, attrs); e.append(...children.filter(c => c != null)); return e; }
let userLang = 'en', busy = false, pending = null;
const sent = [];
const send = text => sent.push(text), notice = () => {};
const units = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const card = unitsCard({query: 'Granada', units});
const buttons = card.children[2].children;
buttons.forEach(b => { b.classList = {add() {}, remove() {}}; b.onclick(); });
console.log(JSON.stringify({labels: buttons.map(b => b.text), sent}));
"""


@pytest.mark.skipif(not shutil.which('node'), reason='no Node')
def test_the_page_of_the_assistant_lists_the_municipalities():
	"""The buttons of the units found: a municipality with its name and its code of the INE, and pressing it sends
	admin3 and that code (it showed 'GAUL undefined' and sent 'admin3 undefined'); those of FAO GAUL as before."""
	with open(os.path.join(ROOT, 'src', 'monitoreo', 'ui', 'assistant.html'), encoding='utf-8') as f:
		page = f.read()
	code = page[page.index('function unitsCard(e)'):page.index('function areasCard(e)')]
	units = municipalities.find('Granada', limit=2) + [
		{'GAUL2_CODE': 141938, 'GAUL2_NAME': 'Granada', 'DISP_EN': 'Granada, Andalucía, Spain', 'level': 2},
		{'GAUL1_CODE': 2541, 'GAUL1_NAME': 'Andalucía'},
		{'ADMIN3_CODE': '04013', 'NAME': 'Almería'}]  # no level nor DISP_EN
	run = subprocess.run(['node', '-e', code + CARD], input=json.dumps(units), capture_output=True, text=True,
	                     timeout=60)
	assert run.returncode == 0, run.stderr
	out = json.loads(run.stdout)
	assert out['labels'] == ['Granada (Granada) (level 3, INE 18087)', 'Alhama de Granada (Granada) (level 3, INE 18013)',
	                         'Granada, Andalucía, Spain (level 2, GAUL 141938)', 'Andalucía (level 1, GAUL 2541)',
	                         'Almería (level 3, INE 04013)']
	assert out['sent'][0] == 'Compute what I asked for with the administrative unit Granada (Granada), admin3 18087'
	assert out['sent'][2].endswith('Granada, Andalucía, Spain, admin2 141938')
	assert out['sent'][4].endswith('Almería, admin3 04013') and not any('undefined' in t for t in out['sent'])
