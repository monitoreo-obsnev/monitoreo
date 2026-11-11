"""The data of Earth Engine outside the catalog (monitoreo.assets: any image or collection by its ID) and the GEE
Community Catalog (monitoreo.community), without Earth Engine and without the internet: their listing by themes, how
an ID is read and cited, the specs, units, titles, facts and file names of their results."""

import pytest

from monitoreo import assets, catalog, community, publish, references, report, services
from monitoreo import variable as variables

FABDEM = 'projects/sat-io/open-datasets/FABDEM'
# Parts of the STAC records of the Earth Engine data catalog, as they are
TERRACLIMATE = {
	'id': 'IDAHO_EPSCOR/TERRACLIMATE', 'gee:type': 'image_collection', 'license': 'CC0-1.0',
	'title': 'TerraClimate:  Monthly Climate and Climatic Water Balance for Global Terrestrial Surfaces, University of '
	         'Idaho',
	'sci:citation': 'Abatzoglou, J.T., S.Z. Dobrowski, S.A. Parks, K.C. Hegewisch, 2018,\nTerraclimate, a '
	                'high-resolution global dataset of monthly climate and\nclimatic water balance from 1958-2015, '
	                'Scientific Data 5:170191,\n[doi:10.1038/sdata.2017.191](https://doi.org/10.1038/sdata.2017.191)\n',
	'providers': [{'name': 'University of California Merced', 'roles': ['licensor', 'producer']},
	              {'name': 'Google Earth Engine', 'roles': ['host']}],
	'extent': {'temporal': {'interval': [['1958-01-01T00:00:00Z', '2024-12-01T00:00:00Z']]}},
	'gee:interval': {'interval': 1, 'type': 'cadence', 'unit': 'month'},
	'summaries': {'eo:bands': [{'name': 'pr', 'description': 'Precipitation accumulation', 'gee:units': 'mm'},
	                           {'name': 'tmmx', 'description': 'Maximum temperature', 'gee:units': '&deg;C',
	                            'gee:scale': 0.1}]},
}
MOD13Q1 = {
	'id': 'MODIS/061/MOD13Q1', 'gee:type': 'image_collection', 'license': 'proprietary',
	'title': 'MOD13Q1.061 Terra Vegetation Indices 16-Day Global 250m', 'sci:doi': '10.5067/MODIS/MOD13Q1.061',
	'sci:citation': "Please visit [LP DAAC 'Citing Our Data' page](https://lpdaac.usgs.gov/citing_our_data)\nfor "
	                'information on citing LP DAAC datasets.\n',
	'providers': [{'name': 'NASA LP DAAC at the USGS EROS Center', 'roles': ['licensor', 'producer']}],
}
WORLDCOVER = {
	'id': 'ESA/WorldCover/v200', 'license': 'CC-BY-4.0', 'title': 'ESA WorldCover 10m v200',
	'sci:citation': 'Zanaga, D., Van De Kerchove, R., Daems, D., De Keersmaecker, W., Brockmann,\nC., Kirches, G., '
	                'Wevers, J., Cartus, O., Santoro, M., Fritz, S., Lesiv, M.,\nHerold, M., Tsendbazar, N.E., Xu, P., '
	                'Ramoino, F., Arino, O., 2022. ESA\nWorldCover 10 m 2021 v200.\n([doi:10.5281/zenodo.7254221]'
	                '(https://doi.org/10.5281/zenodo.7254221))\n',
}


def test_community_catalog():
	snap = community.load()
	assert snap['licence'] == 'CC BY 4.0' and len(snap['commit']) == 40 and snap['datasets']
	assert {d['type'] for d in snap['datasets']} == {'image', 'image_collection'}  # no tables
	assert community.NOT_PUBLIC not in {d['theme'] for d in snap['datasets']}  # the insiders' datasets are not public
	assert len({d['id'] for d in snap['datasets']}) == len(snap['datasets'])
	themes = community.themes('es')
	assert {t['theme'] for t in themes} <= set(community.SPANISH) and all(t['datasets'] for t in themes)
	assert next(t for t in themes if t['theme'] == 'Hydrology')['name'] == 'Hidrología'
	fire = community.datasets('Incendios')  # a theme by a word of its Spanish name
	assert fire and all(d['theme'] == 'Fire Monitoring and Analysis' for d in fire)
	dem = community.datasets(text='fabdem')
	assert [d['id'] for d in dem] == [FABDEM] and dem[0]['docs'].startswith(community.SITE)
	assert all(d['type'] == 'image' for d in community.datasets(kind='image', limit=5))
	assert len(community.datasets(limit=3)) == 3
	assert community.record('projects/earthengine-legacy/assets/' + FABDEM)['id'] == FABDEM
	assert community.record('MODIS/061/MOD13Q1') is None
	with pytest.raises(ValueError, match='unknown theme'):
		community.datasets('mountains')
	with pytest.raises(ValueError, match='unknown kind'):
		community.datasets(kind='table')
	assert services.community_datasets(text='fabdem')[0]['id'] == FABDEM
	assert services.community_themes()[0]['theme'] == community.THEMES[0][0]


def test_ids_and_stac():
	assert assets.normalize(" ee.ImageCollection('IDAHO_EPSCOR/TERRACLIMATE'); ") == 'IDAHO_EPSCOR/TERRACLIMATE'
	assert assets.normalize('ee.Image("WORLDCLIM/V1/BIO")') == 'WORLDCLIM/V1/BIO'
	assert assets.normalize('"projects/earthengine-public/assets/MODIS/061/MOD13Q1"') == 'MODIS/061/MOD13Q1'
	assert assets.stac_url('MODIS/061/MOD13Q1') == f'{assets.STAC}/MODIS/MODIS_061_MOD13Q1.json'
	assert assets.stac_url(FABDEM) == f"{assets.STAC}/sat-io/{FABDEM.replace('/', '_')}.json"
	assert assets.stac_url('projects/openet/assets/ensemble/conus/gridmet/monthly/v2_0').startswith(
		f'{assets.STAC}/OpenET/')
	assert assets.page('ESA/WorldCover/v200') == assets.PAGE + 'ESA_WorldCover_v200'
	assert assets.udunits('&deg;C') == 'degC' and assets.udunits('W/m^2') == 'W m-2' and assets.udunits('mm/y') == \
		'mm year-1' and assets.udunits('Dimensionless') == '1'
	assert assets.udunits('Standard deviation') is None and assets.udunits(None) is None
	for unit in set(assets.UNITS.values()):  # the translations are UDUNITS as MonitorEO writes them
		assert catalog.UDUNITS_TEXT.fullmatch(unit), unit
	assert assets.stac('IDAHO_EPSCOR/TERRACLIMATE') is None  # no internet in the tests (conftest)


def test_citations_of_stac_records():
	(text, doi), = assets._publications(TERRACLIMATE)
	assert doi == '10.1038/sdata.2017.191' and text.startswith('Abatzoglou, J.T.') and 'doi' not in text.lower()
	assert text.endswith('Scientific Data 5:170191.') and '\n' not in text
	assert assets._publications(MOD13Q1) == []  # "Please visit ...": not a citation
	(text, doi), = assets._publications(WORLDCOVER)
	assert doi == '10.5281/zenodo.7254221' and text.endswith('WorldCover 10 m 2021 v200.') and '(' not in text
	assets._stac['MODIS/061/MOD13Q1'] = MOD13Q1
	refs, credits, methods = assets.cite('MODIS/061/MOD13Q1')
	assert refs == [('MODIS/061/MOD13Q1', {'citation': 'NASA LP DAAC at the USGS EROS Center. MOD13Q1.061 Terra '
	                                                   'Vegetation Indices 16-Day Global 250m [Dataset]. Earth Engine '
	                                                   'data catalog, MODIS/061/MOD13Q1.',
	                                       'doi': '10.5067/MODIS/MOD13Q1.061'})]
	assert credits == [f"MOD13Q1.061 Terra Vegetation Indices 16-Day Global 250m (MODIS/061/MOD13Q1): terms of use in "
	                   f"{assets.page('MODIS/061/MOD13Q1')}#terms-of-use"] and methods == []
	assets._stac['IDAHO_EPSCOR/TERRACLIMATE'] = TERRACLIMATE
	refs, credits, _ = assets.cite('IDAHO_EPSCOR/TERRACLIMATE')
	assert [r['doi'] for _, r in refs] == ['10.1038/sdata.2017.191'] and credits[0].endswith('licence CC0-1.0')


def test_citations_of_other_data():
	refs, credits, methods = assets.cite(FABDEM)  # in the GEE Community Catalog
	(rid, ref), = refs
	assert rid == FABDEM and ref['url'] == 'https://gee-community-catalog.org/projects/fabdem/'
	assert ref['citation'].startswith('Hawker, L.') and FABDEM in ref['citation']
	assert methods == ['roy2026', 'roy2026catalog'] and 'Non Commercial' in credits[0]
	(rid, ref), = assets.cite('users/someone/my_image')[0]  # neither: the asset itself
	assert ref == {'citation': 'Earth Engine asset users/someone/my_image.',
	               'url': 'https://code.earthengine.google.com/?asset=users/someone/my_image'}
	cited = references.cite('time_series', {'region': {'wdpa_id': 1}, 'collection': FABDEM, 'band': 'b1',
	                                        'start': '2020-01-01', 'end': '2020-12-31'})
	ids = [r['id'] for r in cited['references']]
	assert {FABDEM, 'roy2026', 'roy2026catalog', 'gorelick2017', 'monitoreo'} <= set(ids)
	assert any('Non Commercial' in c for c in cited['credits'])
	# the datasets of catalog.json are cited as it says, not from STAC
	assets._stac['IDAHO_EPSCOR/TERRACLIMATE'] = TERRACLIMATE
	ids = [r['id'] for r in references.cite('map_layer', {'collection': 'IDAHO_EPSCOR/TERRACLIMATE', 'band': 'pr'})[
		'references']]
	assert 'abatzoglou2018' in ids and 'IDAHO_EPSCOR/TERRACLIMATE#1' not in ids
	data = references.of_data(FABDEM)
	assert {r['id'] for r in data['references']} == {FABDEM, 'roy2026', 'roy2026catalog'}
	for rid in ('roy2026', 'roy2026catalog'):  # in the bibliography of catalog.json, with their DOIs
		assert references.get(rid)['doi']


def test_specs_of_other_data():
	spec = services.make_spec(collection=" ee.ImageCollection('IDAHO_EPSCOR/TERRACLIMATE') ", band='pr',
	                          start='2020-01-01', end='2020-12-31', metric='sum', unit='mm month-1')
	assert spec['collection'] == 'IDAHO_EPSCOR/TERRACLIMATE' and spec['unit'] == 'mm month-1'
	assert services._unit(spec) == 'mm' and services._ylabel(spec) == '[mm]'  # the sum of a rate is a total
	assert services._title(spec) == 'IDAHO_EPSCOR/TERRACLIMATE pr | 2020-01-01 / 2020-12-31'
	d = variables.describe(spec)
	assert d['variable'] == 'IDAHO_EPSCOR/TERRACLIMATE pr' and d['band'] == 'pr' and d['pixel_filters'] == {}
	assert d['unit'] == 'mm' and d['udunits'] == 'mm' and d['period'] == ['2020-01-01', '2020-12-31']
	assert services.make_spec(collection='X/Y', band='b', start='2020-01-01', end='2020-12-31',
	                          unit='°C')['unit'] == 'degC'
	img = services.make_spec(image='WORLDCLIM/V1/BIO', band='bio01', band_scale=0.1, unit='degC', start='2020-01-01',
	                         end='2020-12-31')
	assert variables.is_static(img) and services._named(img, 'median') == 'WORLDCLIM/V1/BIO bio01'
	d = variables.describe(img)
	assert 'period' not in d and 'metric' not in d and d['scale'] == 0.1 and d['udunits'] == 'degC'
	with pytest.raises(ValueError, match='without dates'):
		variables.check_dates(img, 'time series')
	with pytest.raises(ValueError, match='without dates'):
		services.time_series({'wdpa_id': 1}, image='WORLDCLIM/V1/BIO', band='bio01')  # before Earth Engine
	with pytest.raises(ValueError, match='give the band'):
		services.make_spec(collection='IDAHO_EPSCOR/TERRACLIMATE', start='2020-01-01', end='2020-12-31')
	with pytest.raises(ValueError, match='UDUNITS'):
		services.make_spec(collection='X/Y', band='b', start='2020-01-01', end='2020-12-31', unit='mm/día')
	with pytest.raises(ValueError, match='has its unit in the catalog'):
		services.make_spec('NDVI', 'Modis', '2020-01-01', '2020-12-31', unit='1')
	assert services.make_spec(collection='X/Y', band='b', start='2020-01-01', end='2020-12-31', unit='1')['unit'] == '1'


def test_an_image_given_as_a_collection(monkeypatch):
	monkeypatch.setitem(assets._info, 'WORLDCLIM/V1/BIO', {'type': 'image'})
	spec = services.make_spec(collection='WORLDCLIM/V1/BIO', band='bio01', start='2020-01-01', end='2020-12-31')
	with pytest.raises(ValueError, match="give it as image='WORLDCLIM/V1/BIO'"):
		variables.check_asset(spec)
	monkeypatch.setitem(assets._info, 'X/TILES', {'type': 'image_collection'})
	variables.check_asset(services.make_spec(image='X/TILES', band='b'))  # a collection of tiles: their mosaic


def test_describe_asset(monkeypatch):
	meta = {'asset': 'IDAHO_EPSCOR/TERRACLIMATE', 'type': 'image_collection', 'first_date': '1958-01-01',
	        'bands': [{'band': 'pr', 'data_type': 'int', 'resolution_m': 4638.3},
	                  {'band': 'tmmx', 'data_type': 'int', 'resolution_m': 4638.3}]}
	monkeypatch.setattr(assets, 'info', lambda asset: meta)
	assets._stac['IDAHO_EPSCOR/TERRACLIMATE'] = TERRACLIMATE
	d = services.describe_asset("ee.ImageCollection('IDAHO_EPSCOR/TERRACLIMATE')")
	assert d['use'] == 'collection' and d['source'] == 'Earth Engine data catalog' and d['cadence'] == '1 month'
	assert d['dates'] == ['1958-01-01', '2024-12-01'] and d['licence'] == 'CC0-1.0'
	assert d['bands'][1] == {'band': 'tmmx', 'description': 'Maximum temperature', 'units': '&deg;C', 'unit': 'degC',
	                         'band_scale': 0.1, 'resolution_m': 4638.3, 'data_type': 'int'}
	assert d['arguments'] == {'collection': 'IDAHO_EPSCOR/TERRACLIMATE', 'band': 'pr', 'unit': 'mm'}
	assert [r['id'] for r in d['references']] == ['abatzoglou2018']
	meta = {'asset': FABDEM, 'type': 'image_collection', 'first_date': None,
	        'bands': [{'band': 'b1', 'data_type': 'float', 'resolution_m': 30.9}]}
	d = services.describe_asset(FABDEM)  # a collection of tiles without dates, in the community catalog
	assert d['use'] == 'image' and d['arguments'] == {'image': FABDEM, 'band': 'b1'} and d['theme']
	assert d['source'] == 'GEE Community Catalog' and any('units' in n for n in d['notes'])


def test_results_of_other_data():
	args = {'region': {'wdpa_id': 1}, 'collection': 'IDAHO_EPSCOR/TERRACLIMATE', 'band': 'pr', 'start': '2020-01-01',
	        'end': '2020-12-31', 'unit': 'mm month-1', 'band_scale': 1}
	assert report.item_title('map_layer', args).startswith('Map of IDAHO_EPSCOR/TERRACLIMATE pr, 2020')
	assert publish.default_title('time_series', args).startswith('Monthly time series of IDAHO_EPSCOR/TERRACLIMATE pr')
	facts = dict(report.item_facts('time_series', args))
	assert facts['Data'] == ('Earth Engine image collection IDAHO_EPSCOR/TERRACLIMATE, band pr; values × 1 + 0; '
	                         'unit mm month-1')
	assert facts['Discarded pixels'].startswith('none') and 'Temporal metric' in facts
	image = {'region': {'wdpa_id': 1}, 'image': 'COPERNICUS/DEM/GLO30', 'band': 'DEM', 'terrain': 'slope',
	         'start': '2020-01-01', 'end': '2020-12-31'}
	assert publish.is_static(image) and report.item_title('map_layer', image) == \
		'Map of COPERNICUS/DEM/GLO30 DEM slope'
	facts = dict(report.item_facts('map_layer', image))
	assert 'Temporal metric' not in facts and 'Period' not in facts and 'Discarded pixels' not in facts
	assert facts['Data'].endswith('its slope in degrees; unit not given')
	assert publish._variables([{'tool': 'map_layer', 'args': args}]) == [
		{'variable': 'IDAHO_EPSCOR/TERRACLIMATE pr', 'sensor': '', 'name': 'Earth Engine image collection',
		 'unit': 'mm month-1'}]
	recipe = {'recipe': {'variables': [{'collection': 'IDAHO_EPSCOR/TERRACLIMATE', 'band': 'pr', 'metric': 'sum'},
	                                   {'image': 'WORLDCLIM/V1/BIO', 'band': 'bio01'}]}}
	assert dict(report.item_facts('download_variables', recipe))['Variables'] == \
		'IDAHO_EPSCOR/TERRACLIMATE pr: sum; WORLDCLIM/V1/BIO bio01 (fixed image)'


def test_file_names_of_other_data():
	stem = services._file_stem(None, None, 'mean', '2020-01-01', '2020-12-31',
	                           {'collection': 'IDAHO_EPSCOR/TERRACLIMATE', 'band': 'pr'})
	assert stem == 'TERRACLIMATE_pr_mean_2020-01-01_2020-12-31'
	assert services._file_stem(None, None, 'median', None, None, {'image': 'COPERNICUS/DEM/GLO30', 'band': 'DEM',
	                                                               'terrain': 'slope'}) == 'GLO30_DEM_slope'
	assert services._source_name(None, {'collection': 'X/Y', 'band': 'b'}) == 'X/Y b'


def test_themes_of_other_data():
	keys = [t['key'] for t in services.themes()]
	assert keys[-2:] == ['earth_engine', 'community'] and keys[:len(catalog.THEMES)] == [t['key'] for t in catalog.THEMES]
	assert services.themes('es')[-1] == {'key': 'community', 'name': 'Catálogo de la comunidad de GEE', 'variables': [],
	                                     'analyses': [], 'data': 'community'}
	with pytest.raises(ValueError, match='community_datasets'):
		services.list_variables(theme='community')
