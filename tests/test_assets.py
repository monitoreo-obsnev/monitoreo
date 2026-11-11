"""The data of Earth Engine outside the catalog (monitoreo.assets: any image or collection by its ID) and the GEE
Community Catalog (monitoreo.community), without Earth Engine and without the internet: their listing by themes, how
an ID is read and cited, the specs, units, titles, facts and file names of their results."""

import re

import pytest

from monitoreo import assets, catalog, community, publish, references, report, services
from monitoreo import variable as variables

FABDEM = 'projects/sat-io/open-datasets/FABDEM'
FETCH = assets._fetch_json  # before the fixture of conftest replaces it (no internet in the tests)
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
NCEP = {'sci:citation': 'Kalnay, E. et al., 1996: The NCEP/NCAR 40-year reanalysis project. Bull. Amer.\nMeteor. '
                        'Soc., 77, 437-471.\n[doi:10.1175/1520-0477(1996)077<0437:TNYRP\\>2.0.CO;2](https://doi.org/'
                        '10.1175/1520-0477(1996)077<0437:TNYRP>2.0.CO;2)\n'}
ERA5_LAND = {'sci:citation': 'Mu&ntilde;oz Sabater, J., (2019): ERA5-Land monthly averaged data from 1981 to present.\n'
                             'Copernicus Climate Change Service (C3S) Climate Data Store (CDS).\n(&lt;date of '
                             'access&gt;),\n[doi:10.24381/cds.68d2bb30](https://doi.org/10.24381/cds.68d2bb30)\n'}
WORLDCLIM = {'sci:citation': 'Hijmans, R.J., S.E. Cameron, J.L. Parra, P.G. Jones and A. Jarvis, 2005. Very High '
                             'Resolution Interpolated Climate Surfaces for Global Land Areas. International Journal of '
                             'Climatology 25: 1965-1978. [doi:10.1002/joc.1276](https://doi.org/10.1002/joc.1276)\n'
                             'Fick, S.E. and R.J. Hijmans, 2017. WorldClim 2: new 1-km spatial resolution climate '
                             'surfaces for global land areas. International Journal of Climatology 37 (12): 4302-4315. '
                             '[doi:10.1002/joc.5086](https://doi.org/10.1002/joc.5086)\n'}


def test_community_catalog():
	snap = community.load()
	assert snap['licence'] == 'CC BY 4.0' and re.search(r'/blob/[0-9a-f]{40}/community_datasets.json$', snap['source'])
	assert snap['date'] and snap['datasets']
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


def test_citations_with_dois_of_old_articles():
	"""The DOIs with parentheses, < > and ; (the SICI of AMS, the old articles of Elsevier) are whole, in a link of
	Markdown or not, and nothing of them is left in the text; what a citation asks to fill in, the HTML entities of the
	records and the gaps of the DOIs are not in it either; a paragraph with several DOIs is an article for each."""
	(text, doi), = assets._publications(NCEP)
	assert doi == '10.1175/1520-0477(1996)077<0437:TNYRP>2.0.CO;2'
	assert text == 'Kalnay, E. et al., 1996: The NCEP/NCAR 40-year reanalysis project. Bull. Amer. Meteor. Soc., 77, ' \
		'437-471.'
	tucker = 'Tucker, C. J. (1979). Red and photographic infrared linear combinations for monitoring vegetation. ' \
		'Remote Sensing of Environment, 8(2), 127-150.'
	for given in ('doi:10.1016/0034-4257(79)90013-0.', '(https://doi.org/10.1016/0034-4257(79)90013-0)',
	              '[doi:10.1016/0034-4257(79)90013-0](https://doi.org/10.1016/0034-4257(79)90013-0)'):
		assert assets._publications({'sci:citation': f'{tucker} {given}'}) == [
			(tucker, '10.1016/0034-4257(79)90013-0')], given
	schaaf = 'Schaaf, C. B., et al. (2002). First operational BRDF, albedo nadir reflectance products from MODIS. ' \
		'Remote Sensing of Environment, 83(1-2), 135-148.'
	assert assets._publications({'sci:citation': f'{schaaf} [doi:10.1016/S0034-4257(02)00091-3](https://doi.org/'
	                                             '10.1016/S0034-4257(02)00091-3)'}) == [
		(schaaf, '10.1016/S0034-4257(02)00091-3')]
	(text, doi), = assets._publications({'sci:citation': 'Huffman, G. J., et al. (1997). The Global Precipitation '
	                                                      'Climatology Project. Bull. Amer. Meteor. Soc., 78, 5-20. '
	                                                      'doi:10.1175/1520-0477(1997)078<2539:GPAYMA>2.0.CO;2.'})
	assert doi == '10.1175/1520-0477(1997)078<2539:GPAYMA>2.0.CO;2' and text.endswith('Soc., 78, 5-20.')
	(text, doi), = assets._publications(ERA5_LAND)
	assert doi == '10.24381/cds.68d2bb30' and text == (
		'Muñoz Sabater, J., (2019): ERA5-Land monthly averaged data from 1981 to present. Copernicus Climate Change '
		'Service (C3S) Climate Data Store (CDS).')
	assert assets._publications({'sci:citation': 'Copernicus (2020). Data set (doi:10.24381/cds.e2161bac).'}) == [
		('Copernicus (2020). Data set.', '10.24381/cds.e2161bac')]
	(text, _), = assets._publications({'sci:citation': 'Heidinger, A. et al. (2014). PATMOS-x [indicate subset used]. '
	                                                    'NOAA NCEI. [access date].'})
	assert text == 'Heidinger, A. et al. (2014). PATMOS-x. NOAA NCEI.'
	assert assets._publications(WORLDCLIM) == [
		('Hijmans, R.J., S.E. Cameron, J.L. Parra, P.G. Jones and A. Jarvis, 2005. Very High Resolution Interpolated '
		 'Climate Surfaces for Global Land Areas. International Journal of Climatology 25: 1965-1978.',
		 '10.1002/joc.1276'),
		('Fick, S.E. and R.J. Hijmans, 2017. WorldClim 2: new 1-km spatial resolution climate surfaces for global land '
		 'areas. International Journal of Climatology 37 (12): 4302-4315.', '10.1002/joc.5086')]
	# the DOIs given as such, with 'doi:' or the address of doi.org before them, and their links out of the text
	pubs = {'sci:doi': 'https://doi.org/10.5067/X', 'title': 'X', 'sci:publications': [
		{'citation': 'A, B. (2019). One. [doi:10.1000/abc](https://doi.org/10.1000/abc)',
		 'doi': 'https://doi.org/10.1000/abc'},
		{'citation': 'C, D. (2020). Two.', 'doi': 'doi:10.1000/def'},
		{'citation': 'E, F. (2021). Three. https://doi.org/10.1000/ghi'}]}
	assert assets._publications(pubs) == [('A, B. (2019). One.', '10.1000/abc'), ('C, D. (2020). Two.', '10.1000/def'),
	                                      ('E, F. (2021). Three.', '10.1000/ghi')]
	assets._stac['X/Y'] = dict(pubs, id='X/Y')
	assert assets.cite('X/Y')[0][-1] == ('X/Y', {'citation': 'X [Dataset]. Earth Engine data catalog, X/Y.',
	                                             'doi': '10.5067/X'})


def test_a_stac_record_that_cannot_be_read_now(monkeypatch):
	"""A STAC record that cannot be read now (no network, a timeout, a server error) is not remembered: it is read again
	(after assets.RETRY seconds), so that one failure does not take the citation of the data for the session; only a
	record, or that there is none (HTTP 4xx), is. Meanwhile, an ID of the Earth Engine data catalog is cited with its
	page, not as any asset."""
	import io
	import socket
	import urllib.error
	import urllib.request
	answers = []

	def urlopen(req, timeout=None):
		a = answers.pop(0)
		if isinstance(a, Exception):
			raise a
		return io.BytesIO(a.encode())

	monkeypatch.setattr(assets, '_fetch_json', FETCH)  # that of the module, on an urlopen of the test
	monkeypatch.setattr(urllib.request, 'urlopen', urlopen)
	monkeypatch.setattr(assets, '_unread', {})
	gldas = 'NASA/GLDAS/V021/NOAH/G025/T3H'
	answers += [socket.timeout('timed out')]
	refs, credits, _ = assets.cite(gldas)
	assert refs == [(gldas, {'citation': f'{gldas} [Dataset]. Earth Engine data catalog.', 'url': assets.page(gldas)})]
	assert credits == [f'{gldas}: terms of use in {assets.page(gldas)}#terms-of-use'] and gldas not in assets._stac
	assert assets.stac(gldas) is None and not answers  # not read again at once
	monkeypatch.setitem(assets._unread, gldas, assets._unread[gldas] - assets.RETRY)  # RETRY seconds later
	answers += ['{"id": "%s", "title": "GLDAS-2.1", "sci:doi": "10.5067/E7TYRXPJKWOQ", "license": "proprietary"}'
	            % gldas]
	refs, _, _ = assets.cite(gldas)
	assert refs[0][1]['doi'] == '10.5067/E7TYRXPJKWOQ' and assets._stac[gldas]['id'] == gldas
	for error in (urllib.error.URLError('no network'), urllib.error.HTTPError('u', 503, 'down', {}, None), '{"id": '):
		answers.append(error)
		with pytest.raises(OSError):
			assets._fetch_json('https://x/y.json')
	for code in (403, 404):  # Cloud Storage: no such record
		answers.append(urllib.error.HTTPError('u', code, 'no', {}, None))
		assert assets._fetch_json('https://x/y.json') is None
	answers.append(urllib.error.HTTPError('u', 404, 'no', {}, None))
	assert assets.stac('A/B') is None and assets._stac['A/B'] is None  # remembered: there is none
	answers.append(urllib.error.HTTPError('u', 404, 'no', {}, None))
	(rid, ref), = assets.cite('users/someone/my_image')[0]  # not of the data catalog: the asset itself
	assert ref['url'] == 'https://code.earthengine.google.com/?asset=users/someone/my_image'


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
	# the families of data whose terms of use ask for a credit line, in the words of catalog.json (no STAC record)
	sentinel = 'Contains modified Copernicus Sentinel data 2020'
	for asset in ('COPERNICUS/S1_GRD', 'COPERNICUS/S2_HARMONIZED', 'COPERNICUS/S3/OLCI', 'COPERNICUS/S5P/OFFL/L3_NO2'):
		cited = references.cite('map_layer', {'collection': asset, 'band': 'b', 'start': '2020-01-01',
		                                      'end': '2020-12-31'})
		assert cited['credits'][0] == sentinel and asset in {r['id'] for r in cited['references']}, asset
	cited = references.cite('map_layer', {'image': 'COPERNICUS/DEM/GLO30', 'band': 'DEM', 'terrain': 'slope'})
	ids = {r['id'] for r in cited['references']}
	assert 'esa_copernicus_dem' in ids and 'COPERNICUS/DEM/GLO30' in ids
	assert cited['credits'][0].startswith('produced using Copernicus WorldDEM-30')
	for asset, level in (('LANDSAT/LC08/C02/T1', 'Level-1'), ('LANDSAT/LC09/C02/T2_TOA', 'Level-1'),
	                     ('LANDSAT/LE07/C02/T2_L2', 'Level-2')):
		ids, credits = references.of_asset(asset)
		assert credits[0] == f'Landsat Collection 2 {level} data courtesy of the U.S. Geological Survey', asset
		assert not set(ids) & {'usgs_landsat89', 'usgs_landsat89_l1', 'chander2009'}  # their credit, not their articles
	assert references.of_asset('NASA/GLDAS/V021/NOAH/G025/T3H')[1] == [
		f"NASA/GLDAS/V021/NOAH/G025/T3H: terms of use in {assets.page('NASA/GLDAS/V021/NOAH/G025/T3H')}#terms-of-use"]
	assert references.family('COPERNICUS/DEM/GLO30') == ('COPERNICUS/DEM/GLO30_2024_1', True)
	assert references.family('MODIS/061/MOD13Q1') == (None, False)
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


def test_units_given_in_other_words():
	"""The unit of the data of Earth Engine by their ID as the user may write it: '' or blank is none (also in a
	recipe); 'unitless', 'dimensionless', 'fraction' and 'index' in any case are 1; the words of the STAC records (and
	so of describe_asset) are translated to UDUNITS ('C' alone is coulomb there: here degC); the code of a variable of
	the catalog is not a unit."""
	def unit(u):
		return services.make_spec(collection='X/Y', band='b', start='2020-01-01', end='2020-12-31', unit=u).get('unit')

	for given in ('', '  ', None):
		assert unit(given) is None
		assert 'unit' not in variables.specs({'collection': 'X/Y', 'band': 'b', 'metric': 'mean', 'unit': given,
		                                      'period': ['2020-01-01', '2020-12-31']})[0]
	for given in ('unitless', 'Unitless', 'DIMENSIONLESS', 'Fraction', 'index', '1'):
		assert unit(given) == '1', given
	for given, udunits in (('C', 'degC'), ('°C', 'degC'), ('ºC', 'degC'), ('deg C', 'degC'), ('°F', 'degF'),
	                       ('W/m^2', 'W m-2'), ('deg', 'degree'), ('°', 'degree'), ('mm/d', 'mm day-1'),
	                       ('mm/pentad', 'mm (5 day)-1'), ('kg/m^2/8day', 'kg m-2 (8 day)-1'), ('mm', 'mm'),
	                       ('kg m-2 s-1', 'kg m-2 s-1')):
		assert unit(given) == udunits, given
	for given in ('NDVI', 'ndvi', 'Chl-a', 'LST', 'mm!', 'm²'):
		with pytest.raises(ValueError, match='is written in UDUNITS'):
			unit(given)
	with pytest.raises(ValueError, match='has its unit in the catalog'):
		services.make_spec('NDVI', 'Modis', '2020-01-01', '2020-12-31', unit='1')
	assert 'unit' not in services.make_spec('NDVI', 'Modis', '2020-01-01', '2020-12-31', unit=' ')  # none given


def test_the_slope_of_an_image():
	"""The slope and the aspect of the band of an image are in degrees, whatever its unit (that of describe_asset: m for
	a DEM), and their names say them: the slope of a DEM is not named as its elevation."""
	dem = {'image': 'COPERNICUS/DEM/GLO30', 'band': 'DEM'}
	elevation = services.make_spec(**dem, unit='m')
	for unit in (None, '', 'degree', '°', 'deg', 'degrees'):
		slope = services.make_spec(**dem, terrain='slope', unit=unit)
		assert slope['unit'] == 'degree' and services._unit(slope) == 'degree' and services._ylabel(slope) == \
			'[degree]', unit
		d = variables.describe(slope)
		assert (d['unit'], d['udunits'], d['terrain']) == ('degree', 'degree', 'slope')
	with pytest.raises(ValueError) as error:
		services.make_spec(**dem, terrain='slope', unit='m')
	assert str(error.value) == ("the slope of COPERNICUS/DEM/GLO30 is in degrees: give no unit, or 'degree' (not 'm', "
	                            'the unit of its band)')
	with pytest.raises(ValueError, match='the aspect of COPERNICUS/DEM/GLO30 is in degrees'):
		services.make_spec(**dem, terrain='aspect', unit='1')
	with pytest.raises(ValueError, match='unknown terrain hillshade: use slope, aspect'):
		services.make_spec(**dem, terrain='hillshade')
	assert services._title(elevation) == services._named(elevation, 'median') == 'COPERNICUS/DEM/GLO30 DEM'
	assert services._title(slope) == services._named(slope, 'median') == variables.describe(slope)['variable'] == \
		variables.data_name(slope) == 'COPERNICUS/DEM/GLO30 DEM slope'
	assert variables.describe(elevation)['variable'] == 'COPERNICUS/DEM/GLO30 DEM'
	assert services._source_name(None, dict(dem, terrain='aspect')) == 'COPERNICUS/DEM/GLO30 DEM aspect'


def test_an_id_given_as_a_variable():
	"""An ID of Earth Engine given as a variable of the catalog (none has '/'), with or without a sensor and a band:
	the same message, which says how to give it."""
	message = ('IDAHO_EPSCOR/TERRACLIMATE is not a variable of the catalog: give an ID of Earth Engine as a collection '
	           'or an image (describe_asset says which), with its band, instead of the variable')
	assert not any('/' in e['index'] for e in catalog.variables())
	for given in ({}, {'band': 'pr'}, {'sensor': 'TerraClimate'}, {'sensor': 'TerraClimate', 'band': 'pr'}):
		with pytest.raises(ValueError) as error:
			services.make_spec('IDAHO_EPSCOR/TERRACLIMATE', start='2020-01-01', end='2020-12-31', **given)
		assert str(error.value) == message, given


def test_the_help_of_the_functions_says_the_data_by_id():
	"""help() of every function of the services that takes the data of Earth Engine by their ID (**source) says them,
	as the MCP server, the command line and R do in theirs."""
	import inspect
	taking = [n for n, f in vars(services).items() if inspect.isfunction(f) and not n.startswith('_') and
	          f.__module__ == services.__name__ and 'source' in inspect.signature(f).parameters and
	          inspect.signature(f).parameters['source'].kind is inspect.Parameter.VAR_KEYWORD]
	assert {'time_series', 'map_layer', 'region_stats', 'download_image', 'trend_table', 'compare_series',
	        'export_image', 'compare_map', 'download_comparison'} <= set(taking)
	for name in taking:
		doc = inspect.getdoc(getattr(services, name))
		assert doc.count(services.SOURCE_DOC.split()[0]) and all(w in doc for w in (
			'COLLECTION', 'IMAGE', 'BAND_SCALE', 'BAND_OFFSET', 'UNIT', 'TERRAIN', 'describe_asset')), name
		assert "in degrees: its unit is then degree" in ' '.join(doc.split()), name
	assert 'TERRAIN' not in inspect.getdoc(services.same_area)  # its source is not **source


def test_an_image_given_as_a_collection(monkeypatch):
	"""An image, or a collection of tiles without dates (which the period would leave empty), given as a collection is
	an error in the words of every tool (no argument of Python: the command line and R read it too), whatever was
	computed before with the same ID."""
	monkeypatch.setitem(assets._info, 'WORLDCLIM/V1/BIO', {'type': 'image'})
	spec = services.make_spec(collection='WORLDCLIM/V1/BIO', band='bio01', start='2020-01-01', end='2020-12-31')
	message = ('WORLDCLIM/V1/BIO is an image, not a collection of images: give it as an image (a fixed layer, without '
	           'dates: maps, GeoTIFFs and statistics of the region)')
	with pytest.raises(ValueError) as error:
		variables.check_asset(spec)
	assert str(error.value) == message and '=' not in message
	# the pixel size of image= is that of collection= with the same ID, but not what can be computed with it
	monkeypatch.setattr(variables, '_native', {('WORLDCLIM/V1/BIO', 'bio01'): 927.67})
	assert variables.native_scale(services.make_spec(image='WORLDCLIM/V1/BIO', band='bio01')) == 927.67
	with pytest.raises(ValueError, match='is an image, not a collection'):
		variables.native_scale(spec)
	monkeypatch.setitem(assets._info, FABDEM, {'type': 'image_collection', '_first': {'id': 'tile'}})
	variables.check_asset(services.make_spec(image=FABDEM, band='b1'))  # a collection of tiles: their mosaic
	assert assets.first_date(FABDEM) is None
	with pytest.raises(ValueError) as error:  # ... not a collection: no image would have the dates of the period
		variables.check_asset(services.make_spec(collection=FABDEM, band='b1', start='2020-01-01', end='2020-12-31'))
	assert str(error.value) == (f'{FABDEM} is a collection of images without dates (tiles): give it as an image (their '
	                            'mosaic, a fixed layer, without dates)')
	monkeypatch.setitem(assets._info, 'X/DATED', {'type': 'image_collection',
	                                              '_first': {'startTime': '2020-01-06T00:00:00Z'}})
	assert assets.first_date('X/DATED') == '2020-01-06'
	variables.check_asset(services.make_spec(collection='X/DATED', band='b', start='2020-01-01', end='2020-12-31'))
	variables.check_asset(services.make_spec(image='X/DATED', band='b'))  # the mosaic of its images, if asked


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
	# of the Earth Engine data catalog, but its STAC record could not be read: its page, not 'Earth Engine asset'
	meta = dict(meta, asset='NASA/GLDAS/V021/NOAH/G025/T3H', first_date='2000-01-01')
	d = services.describe_asset('NASA/GLDAS/V021/NOAH/G025/T3H')
	assert (d['source'], d['page']) == ('Earth Engine data catalog', assets.page('NASA/GLDAS/V021/NOAH/G025/T3H'))
	assert any('could not be read' in n for n in d['notes']) and d['credits'][0].endswith('#terms-of-use')
	meta = dict(meta, asset='users/someone/my_image')
	assert services.describe_asset('users/someone/my_image')['source'] == 'Earth Engine asset'


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
	assert facts['Data'] == 'Earth Engine image COPERNICUS/DEM/GLO30, band DEM, its slope; unit degree'
	# the unit as the services compute it: 'unitless' is dimensionless, '°C' is degC
	for unit, said in (('unitless', '; dimensionless'), ('Dimensionless', '; dimensionless'), ('1', '; dimensionless'),
	                   ('°C', '; unit degC'), ('', '; unit not given'), (None, '; unit not given')):
		assert dict(report.item_facts('map_layer', dict(args, unit=unit)))['Data'].endswith(said), unit
	assert publish._variables([{'tool': 'map_layer', 'args': image}])[0]['unit'] == 'degree'
	# the ID as the tools take it, wherever the call names it: as given, the call of the Code Editor too
	raw = dict(args, collection='ee.ImageCollection("IDAHO_EPSCOR/TERRACLIMATE")')
	assert report.item_title('map_layer', raw).startswith('Map of IDAHO_EPSCOR/TERRACLIMATE pr, 2020')
	assert dict(report.item_facts('map_layer', raw))['Data'].startswith(
		'Earth Engine image collection IDAHO_EPSCOR/TERRACLIMATE, band pr')
	assert publish._variables([{'tool': 'map_layer', 'args': raw}, {'tool': 'time_series', 'args': args}]) == \
		publish._variables([{'tool': 'map_layer', 'args': args}])
	assert services._source_name(None, raw) == 'IDAHO_EPSCOR/TERRACLIMATE pr'
	assert services._what(None, None, raw) == 'TERRACLIMATE_pr'
	assert publish._variables([{'tool': 'map_layer', 'args': args}]) == [
		{'variable': 'IDAHO_EPSCOR/TERRACLIMATE pr', 'sensor': '', 'name': 'Earth Engine image collection',
		 'unit': 'mm month-1'}]
	recipe = {'recipe': {'variables': [{'collection': 'IDAHO_EPSCOR/TERRACLIMATE', 'band': 'pr', 'metric': 'sum'},
	                                   {'image': 'WORLDCLIM/V1/BIO', 'band': 'bio01'},
	                                   {'image': "ee.Image('COPERNICUS/DEM/GLO30_2024_1')", 'band': 'DEM',
	                                    'terrain': 'slope'}]}}
	assert dict(report.item_facts('download_variables', recipe))['Variables'] == \
		'IDAHO_EPSCOR/TERRACLIMATE pr: sum; WORLDCLIM/V1/BIO bio01 (fixed image); COPERNICUS/DEM/GLO30_2024_1 DEM ' \
		'slope (fixed image)'


def test_file_names_of_other_data():
	stem = services._file_stem(None, None, 'mean', '2020-01-01', '2020-12-31',
	                           {'collection': 'IDAHO_EPSCOR/TERRACLIMATE', 'band': 'pr'})
	assert stem == 'TERRACLIMATE_pr_mean_2020-01-01_2020-12-31'
	assert services._file_stem(None, None, 'median', None, None, {'image': 'COPERNICUS/DEM/GLO30', 'band': 'DEM',
	                                                               'terrain': 'slope'}) == 'GLO30_DEM_slope'
	assert services._source_name(None, {'collection': 'X/Y', 'band': 'b'}) == 'X/Y b'
	assert services._file_stem(None, None, 'mean', '2020-01-01', '2020-12-31', {
		'collection': "ee.ImageCollection('IDAHO_EPSCOR/TERRACLIMATE')", 'band': 'pr'}) == stem


def test_themes_of_other_data():
	keys = [t['key'] for t in services.themes()]
	assert keys[-2:] == ['earth_engine', 'community'] and keys[:len(catalog.THEMES)] == [t['key'] for t in catalog.THEMES]
	assert services.themes('es')[-1] == {'key': 'community', 'name': 'Catálogo de la comunidad de GEE', 'variables': [],
	                                     'analyses': [], 'data': 'community'}
	with pytest.raises(ValueError, match='list its themes and their datasets') as error:
		services.list_variables(theme='community')
	# in the words of every tool: no function or argument of one of them (the command line and R show it too)
	for t in catalog.OTHER_THEMES:
		assert not re.search(r'=|_datasets|_themes|describe_asset', t['help']), t['key']
	assert '=' not in str(error.value)


def test_the_readme_of_a_recipe_tells_the_slope_from_the_elevation(tmp_path):
	"""The README of the folder of a recipe names each file by its data, with its terrain and its unit: the elevation
	and the slope of a DEM are two files, not the same one twice."""
	import json

	from monitoreo import readme
	files = {}
	for i, var in enumerate(({'name': 'dem', 'image': 'COPERNICUS/DEM/GLO30', 'band': 'DEM', 'unit': 'm'},
	                         {'name': 'slope', 'image': 'COPERNICUS/DEM/GLO30', 'band': 'DEM', 'terrain': 'slope'}), 1):
		spec, = variables.specs(var)
		files[f'{i}_{spec["name"]}.tif'] = {'spec': {k: v for k, v in spec.items() if k != 'quality'},
		                                    'source': variables.describe(spec)}
	rec = {'grid': {'crs': 'EPSG:32630', 'resolution': 30.0, 'width': 10, 'height': 10, 'extent': [0, 0, 300, 300]},
	       'study_area': 'area.gpkg', 'files': files, 'tasks': {}}
	(tmp_path / 'monitoreo.json').write_text(json.dumps(rec), encoding='utf-8')
	text = ' '.join(open(readme.recipe_folder(str(tmp_path)), encoding='utf-8').read().split())
	assert '1_dem.tif: COPERNICUS/DEM/GLO30 DEM; unit m (UDUNITS m).' in text
	assert '2_slope.tif: COPERNICUS/DEM/GLO30 DEM slope; unit degree (UDUNITS degree).' in text


def test_the_bands_that_the_first_image_has_not(monkeypatch):
	"""Sentinel-1 changes its bands from image to image (VV and VH, or HH and HV): describe_asset lists those of its
	STAC record that its first image has not, and the tools use the images that have the band asked for."""
	asset = 'COPERNICUS/S1_GRD'
	meta = {'asset': asset, 'type': 'image_collection', 'first_date': '2014-10-03',
	        'bands': [{'band': 'HH', 'data_type': 'float', 'resolution_m': 10.0},
	                  {'band': 'HV', 'data_type': 'float', 'resolution_m': 10.0},
	                  {'band': 'angle', 'data_type': 'float', 'resolution_m': 20000.0}]}
	monkeypatch.setattr(assets, 'info', lambda a: meta)
	assets._stac[asset] = {'id': asset, 'title': 'Sentinel-1 SAR GRD', 'license': 'proprietary',
	                       'summaries': {'eo:bands': [{'name': n, 'gsd': [10], 'gee:units': 'dB'}
	                                                  for n in ('HH', 'HV', 'VV', 'VH')] + [{'name': 'angle'}]}}
	d = services.describe_asset(asset)
	assert [b['band'] for b in d['bands']] == ['HH', 'HV', 'angle', 'VV', 'VH']
	assert d['bands'][3] == {'band': 'VV', 'units': 'dB', 'unit': 'dB', 'resolution_m': 10.0}
	assert 'Contains modified Copernicus Sentinel data' in ' '.join(d['credits'])  # the credit of its family
