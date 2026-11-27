"""Tests that do not need Earth Engine."""

import csv
import datetime as dt
import json
import os
import re
import types

import pytest

from monitoreo import catalog, charts, composite, drive, fire, report, sensors, services, timeseries, trends, variable
from monitoreo.grid import Grid


def test_catalog():
	entries = catalog.variables()
	assert len(entries) == 119  # the 50 of catalog.json (CLre, WAVI and CLreB7 of Sentinel-2: refs 158 to 160; MSI and
	# MSAVI2 of Landsat and Sentinel-2, the NDWI and LSWI of MODIS MOD09A1 and MYD09A1, the GPP and NPP of MOD17A3HGF and
	# MYD17A3HGF: 165 to 176; the Tasseled Cap brightness, greenness and wetness of Landsat: 185 to 187), NBR and RBR of Landsat and Sentinel-2, SCF of Landsat, the
	# elevation and slope of the Copernicus DEM, the cloud frequency of MODIS (Terra and Aqua), Sentinel-2 and Landsat,
	# 4 variables of ERA5-Land, 8 of TerraClimate, the precipitation of CHIRPS, the 19 of WorldClim, the RdNBR of
	# Sentinel-2, Landsat and MODIS (Terra and Aqua), the topographic wetness index (TWI) of MERIT Hydro, the
	# ecoregions and biomes of RESOLVE Ecoregions 2017 (ECOREGION and BIOME, categorical layers: refs 149 and 150), the
	# SCF of MODIS (Terra and Aqua: refs 151 and 152), the snow cover days (SCD) of Landsat and MODIS (153 to 155) and
	# the SCF and the SCD of Sentinel-2 (156 and 157), and the snow melt-out day (SMOD) of Landsat, MODIS (Terra and
	# Aqua) and Sentinel-2 (161 to 164), the PDSI of TerraClimate (177), the SPEI of 1, 3, 6 and 12 months of SPEIbase
	# (178 to 181), the burn date of MCD64A1 and FireCCI51 (182, 183) and the aspect of the Copernicus DEM (184)
	assert len({e['ref'] for e in entries}) == len(entries)  # the refs are unique
	nbr = catalog.find('NBR', 'Sentinel-2')
	assert nbr['ref'] == 102 and nbr['ft'] == 'N(B8,B12)' and nbr['col'] == 'COPERNICUS/S2_SR_HARMONIZED'
	assert catalog.find('nbr', 'landsat')['ft'] == 'N(nir,swir2)'
	assert catalog.find('ndvi', 'sentinel-2')['col'] == 'COPERNICUS/S2_SR_HARMONIZED'
	assert catalog.find('NDVI', 'Modis')['col'] == 'MODIS/061/MOD13Q1'  # first entry of the catalog
	assert catalog.find(None, ref=32)['scale'] == 0.1  # FIXES: scale of LAI
	with pytest.raises(KeyError):
		catalog.find('NDVI', 'Planet')


def test_chla_sentinel2_is_the_model_of_the_article():
	"""The Chl-a of Sentinel-2 is the model of Table 3b of Llodrà-Llabrés et al. (2026): 1.0702 - 0.5751 S12 + 1.9729 S4
	- 1.1902 S8 of the bands standardized with the mean and SD (n - 1) of its samples. The article does not give those
	constants: its data in HydroShare, without the samples of 2022 that it left out (56 of 2020, 2021 and 2023), give
	exactly its intercept, their mean chlorophyll, and its coefficients by least squares on the z-scores. So, at the mean
	reflectance of the samples the formula gives the intercept, one SD more of a band adds its coefficient, and on a
	sample of a lake it gives a few mg m-3, not about 1.07 everywhere (the draft of the model without the
	standardization, which catalog.json had)."""
	e = catalog.find('Chl-a', 'Sentinel-2')
	assert e['ref'] == 19 and e['col'] == 'COPERNICUS/S2_SR_HARMONIZED' and e['scale'] == 0.0001
	assert e['f'] == e['ft'] and set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', e['ft'])) == {'B12', 'B4', 'B8'}
	assert (e['minp'], e['maxp']) == (0, 4) and 'llodrallabres2026' in e['references']
	assert all(w in e['notes']['ft'] for w in ('Sierra Nevada', 'standardized', 'dust'))  # where it is valid
	mean = {'B12': 0.023899, 'B4': 0.029789, 'B8': 0.025612}  # reflectance (0 to 1): the bands after their scale
	sd = {'B12': 0.014371, 'B4': 0.015196, 'B8': 0.014664}
	chla = lambda **b: eval(e['ft'], {'__builtins__': {}}, b)  # the expression of Earth Engine, in Python
	assert chla(**mean) == pytest.approx(1.0702)
	for band, coef in (('B12', -0.5751), ('B4', 1.9729), ('B8', -1.1902)):
		assert chla(**dict(mean, **{band: mean[band] + sd[band]})) - 1.0702 == pytest.approx(coef)
	lake = {'B12': 0.013925, 'B4': 0.026360, 'B8': 0.019422}  # a sample of the article (P-8, 2020-06-24; 0.258 measured)
	assert chla(**lake) == pytest.approx(1.5266, abs=1e-3)  # its fitted value


def test_albedo_sentinel2_is_the_conversion_of_the_article():
	"""The albedo of Sentinel-2 is the narrow-to-broadband conversion of Bonafoni & Sekertekin (2020): 0.2266 B2 +
	0.1236 B3 + 0.1573 B4 + 0.3417 B8 + 0.1170 B11 + 0.0338 B12 of the surface reflectance, without intercept (each
	weight is the share of the solar irradiance at the surface in the interval of its band, so they add up to 1). Its
	pixel is that of its coarsest bands, B11 and B12: 20 m. It replaces weights without a reference that were the solar
	irradiance at the centre of each band (B2 to B8, B11 and B12), which gave almost 90 % of the weight to the visible
	and red-edge bands."""
	e = catalog.find('ALBEDO', 'Sentinel-2')
	assert e['ref'] == 13 and e['col'] == 'COPERNICUS/S2_SR_HARMONIZED' and (e['scale'], e['offset']) == (0.0001, 0)
	assert e['m'] == 20 and e['references'] == ['bonafoni2020'] and 'references' not in e.get('notes', {})
	assert e['f'] == e['ft'] and set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', e['ft'])) == {'B2', 'B3', 'B4', 'B8', 'B11',
	                                                                                    'B12'}
	albedo = lambda **b: eval(e['ft'], {'__builtins__': {}}, b)  # the expression of Earth Engine, in Python
	weights = {'B2': 0.2266, 'B3': 0.1236, 'B4': 0.1573, 'B8': 0.3417, 'B11': 0.1170, 'B12': 0.0338}
	for band, w in weights.items():
		assert albedo(**{b: float(b == band) for b in weights}) == pytest.approx(w)
	assert albedo(**dict.fromkeys(weights, 0.3)) == pytest.approx(0.3)  # a grey surface: its reflectance
	# the Landsat albedo of Liang (2001), normalized by 1.016, as the formula computed (ft) and as it is written (f)
	landsat = catalog.find('ALBEDO', 'Landsat')
	assert '- 0.0018)' in landsat['ft'] and '- 0.0018)' in landsat['f']


def test_sentinel2_pixel_is_that_of_its_coarsest_band():
	"""The pixel (m) of each variable of Sentinel-2 is that of the coarsest band its formula reads: 20 m with B5, B6,
	B7, B8A, B11 or B12 (LSWI, NDSI, albedo, Chl-a, NDCI, CLre, CLreB7, NBR, RBR, RdNBR, SCF, SCD), 10 m with B2, B3, B4 and B8
	only (NDVI, EVI, NDWI, WAVI) and with the cs_cdf of Cloud Score+ (cloud frequency)."""
	coarse = {'B5', 'B6', 'B7', 'B8A', 'B11', 'B12'}
	got = {}
	for e in catalog.variables():
		if e['sensor'] == 'Sentinel-2':
			bands = set(re.findall(r'\bB[0-9]+A?\b', e['ft']))
			assert e['m'] == (20 if bands & coarse else 10), (e['ref'], e['index'], bands)
			got[e['index']] = e['m']
	assert got == {'LSWI': 20, 'NDSI': 20, 'NDWI': 10, 'ALBEDO': 20, 'Chl-a': 20, 'EVI': 10, 'NDVI': 10, 'NDCI': 20,
	               'NBR': 20, 'RBR': 20, 'SCF': 20, 'SCD': 20, 'SMOD': 20, 'CF': 10, 'RdNBR': 20, 'CLre': 20, 'CLreB7': 20,
	               'WAVI': 10, 'MSI': 20, 'MSAVI2': 10}


def test_moisture_stress_and_modified_soil_adjusted_vegetation_index(monkeypatch):
	"""MSI (SWIR1 / NIR, Hunt & Rock 1989) and MSAVI2 (Qi et al. 1994) of Landsat and Sentinel-2: expressions of the
	bands of the catalog (the square root of the MSAVI2 as ** 0.5, which the expressions of Earth Engine read and
	parse_formula does not take for a band), without unit, cited, in the themes Water and Vegetation."""
	monkeypatch.setitem(sensors._band_names, 'COPERNICUS/S2_SR_HARMONIZED',
	                    ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B9', 'B11', 'B12', 'SCL'])
	want = {('MSI', 'Landsat'): (165, 30, {'swir1': 'swir1', 'nir': 'nir'}, ['hunt1989'], 'water'),
	        ('MSI', 'Sentinel-2'): (166, 20, {'B11': 'B11', 'B8': 'B8'}, ['hunt1989'], 'water'),
	        ('MSAVI2', 'Landsat'): (167, 30, {'nir': 'nir', 'red': 'red'}, ['qi1994'], 'vegetation'),
	        ('MSAVI2', 'Sentinel-2'): (168, 10, {'B8': 'B8', 'B4': 'B4'}, ['qi1994'], 'vegetation')}
	for (index, sensor), (ref, m, bands, refs, theme) in want.items():
		e = catalog.find(index, sensor)
		assert (e['ref'], e['m'], e['unit'], e['references'], e['theme']) == (ref, m, '[unitless]', refs, theme)
		assert sensors.parse_formula(e) == ('expr', bands) and e['notes']['ft']
		assert not sensors.no_topographic(e) if sensor == 'Landsat' else True  # reflectances of Landsat
	assert catalog.find('MSAVI2', 'Sentinel-2')['ft'] == '(2 * B8 + 1 - ((2 * B8 + 1) ** 2 - 8 * (B8 - B4)) ** 0.5) / 2'
	assert catalog.find('MSI', 'Landsat')['f'] == 'SR_B6 / SR_B5'
	# the MSAVI2 of a pixel as the formula of the article: NIR 0.3 and red 0.1
	nir, red = 0.3, 0.1
	assert abs(eval(catalog.find('MSAVI2', 'Landsat')['ft'], {'nir': nir, 'red': red}) -
	           (2 * nir + 1 - ((2 * nir + 1) ** 2 - 8 * (nir - red)) ** 0.5) / 2) < 1e-12


def test_the_tasseled_cap_of_landsat():
	"""TCB, TCG and TCW of Landsat (Crist 1985): linear combinations of the six reflective bands (blue, green, red, NIR,
	SWIR1, SWIR2, which sensors renames for Landsat 5 and 7 too), without unit, cited, in the theme Vegetation, with the
	coefficients of the article."""
	crist = {'TCB': (0.2043, 0.4158, 0.5524, 0.5741, 0.3124, 0.2303),
	         'TCG': (-0.1603, -0.2819, -0.4934, 0.7940, -0.0002, -0.1446),
	         'TCW': (0.0315, 0.2021, 0.3102, 0.1594, -0.6806, -0.6109)}
	bands = ('blue', 'green', 'red', 'nir', 'swir1', 'swir2')
	for ref, (index, coefficients) in zip((185, 186, 187), crist.items()):
		e = catalog.find(index, 'Landsat')
		assert (e['ref'], e['m'], e['unit'], e['references'], e['theme']) == (ref, 30, '[unitless]', ['crist1985'],
		                                                                     'vegetation')
		assert sensors.parse_formula(e) == ('expr', {b: b for b in bands}) and not sensors.no_harmonize(e)
		for band, c in zip(bands, coefficients):  # each coefficient, with a reflectance of 1 in its band alone
			assert abs(eval(e['ft'], {b: float(b == band) for b in bands}) - c) < 1e-12, (index, band)
	assert catalog.load()['references']['crist1985']['doi'] == '10.1016/0034-4257(85)90102-6'


def test_the_new_variables_of_modis_climate_and_fire():
	"""The NDWI (bands 2 and 5, as MOD09GA_006_NDWI) and the LSWI (bands 2 and 6) of the 8-day reflectance of MODIS, with
	the filters of StateQA; the yearly GPP and NPP without their fill values; the PDSI of TerraClimate and the SPEI of
	SPEIbase; the burn date of MCD64A1 and FireCCI51, with the only metric min; each in its theme, cited, in UDUNITS."""
	old = catalog.find('NDWI', 'Modis')
	assert old['col'] == 'MODIS/MOD09GA_006_NDWI' and 'MOD09A1' in old['notes']['dr']  # still the first: no change
	for index, band, refs in (('NDWI', 'sur_refl_b05', ['gao1996']), ('LSWI', 'sur_refl_b06', ['xiao2004'])):
		for col in ('MODIS/061/MOD09A1', 'MODIS/061/MYD09A1'):
			e = catalog.find(index, 'Modis', col)
			assert (e['m'], e['tr'], e['scale'], e['unit'], e['references']) == (500, '8-days', 0.0001, '[unitless]', refs)
			assert e['ft'] == f'N(sur_refl_b02,{band})' and e['theme'] == 'water' and e['large_areas']
			assert sensors.filters(e) == {f: True for f in sensors.FILTERS}  # those of StateQA
			assert sensors.filters(e, {'water': 'auto'})['water'] is (index != 'NDWI')  # the NDWI measures water
			assert set(sensors.PRODUCTS[col]) == set(sensors.FILTERS)
	for index, band in (('GPP', 'Gpp'), ('NPP', 'Npp')):
		for col in ('MODIS/061/MOD17A3HGF', 'MODIS/061/MYD17A3HGF'):
			e = catalog.find(index, 'Modis', col)
			assert (e['ft'], e['scale'], e['unit'], e['tr'], e['theme']) == (band, 0.0001, '[kg C/m²/year]', 'yearly',
			                                                                  'vegetation')
			assert sensors.valid_ranges(sensors.PRODUCTS[col]) == [('Gpp', 65500, None), ('Npp', 32700, None)]
			assert not any(sensors.filters(e).values())
	assert catalog.udunits('[kg C/m²/year]') == 'kg m-2 year-1'
	pdsi = catalog.find('PDSI', 'TerraClimate')
	assert (pdsi['ref'], pdsi['ft'], pdsi['scale'], pdsi['unit'], pdsi['theme']) == (177, 'pdsi', 0.01, '[unitless]',
	                                                                                 'climate')
	for ref, n in ((178, 1), (179, 3), (180, 6), (181, 12)):
		e = catalog.find(f'SPEI{n}', 'SPEIbase')
		assert (e['ref'], e['col'], e['ft'], e['m'], e['tr'], e['theme']) == (ref, 'CSIC/SPEI/2_11', f'SPEI_{n:02d}_month',
		                                                                      55660, 'monthly', 'climate')
		assert e['references'] == ['vicenteserrano2010', 'begueria2014'] and not any(sensors.filters(e).values())
	for ref, col, m in ((182, 'MODIS/061/MCD64A1', 500), (183, 'ESA/CCI/FireCCI/5_1', 250)):
		e = catalog.find('BURNDATE', 'Modis', col)
		assert (e['ref'], e['m'], e['metric'], e['unit'], e['theme']) == (ref, m, 'min', '[day of year]', 'fire')
		assert sensors.valid_ranges(sensors.PRODUCTS[col]) == [('BurnDate', 366, 1)]  # no 0 (unburned) nor flags
	assert catalog.find('BURNDATE', 'Modis')['col'] == 'MODIS/061/MCD64A1'  # the first one
	with pytest.raises(ValueError, match="only takes the metric 'min'"):
		services.make_spec('BURNDATE', 'Modis', '2021-01-01', '2021-12-31', metric='mean')
	assert services.make_spec('BURNDATE', 'Modis', '2021-01-01', '2021-12-31', metric='min')['metric'] == 'min'
	assert services.list_variables(text='SPEI') and {r['variable'] for r in services.list_variables(sensor='SPEIbase')} \
		== {'SPEI1', 'SPEI3', 'SPEI6', 'SPEI12'}


def test_the_aspect_and_its_conditions_across_the_north():
	"""The aspect of the Copernicus DEM: a fixed layer, an angle (circular), whose conditions of where with a min
	greater than the max go across the north, in the README as «or»; the other variables keep min and max."""
	e = catalog.find('ASPECT', 'Copernicus')
	assert (e['ref'], e['col'], e['band'], e['terrain'], e['unit'], e['static'], e['theme'], e['circular']) == (
		184, 'COPERNICUS/DEM/GLO30_2024_1', 'DEM', 'aspect', '[°]', True, 'terrain', True)
	assert sensors.parse_formula(e) == ('static', ['DEM']) and e['references'] == ['rizzoli2017', 'zevenbergen1987']
	assert variable.across_zero(e, 315, 45) and not variable.across_zero(e, 45, 315)
	assert not variable.across_zero(e, 315, None) and not variable.across_zero(catalog.find('SLOPE', 'Copernicus'), 30, 10)
	d = services.describe_variable('ASPECT', 'Copernicus')
	assert d['circular'] and d['static'] and 'north' in d['notes']['ft']
	assert 'circular' not in services.describe_variable('SLOPE', 'Copernicus')
	north = {'variable': 'ASPECT', 'sensor': 'Copernicus', 'min': 315, 'max': 45}
	assert report.where_text([north]) == 'ASPECT (Copernicus) ≥ 315 or ≤ 45 °'
	assert report.where_text([dict(north, min=135, max=225)]) == 'ASPECT (Copernicus) ≥ 135 and ≤ 225 °'
	spec = services.make_spec('NDVI', 'Sentinel-2', '2021-06-01', '2021-08-31', where=[north])
	(cs, lo, hi), = variable.where_specs(spec)
	assert (cs['index'], lo, hi) == ('ASPECT', 315, 45) and not cs.get('period')


def test_red_edge_chlorophyll_and_water_adjusted_vegetation_index(monkeypatch):
	"""CLre (B8 / B5 - 1), CLreB7 (B7 / B5 - 1) and WAVI (1.5 (B8 - B2) / (B8 + B2 + 0.5)) of Sentinel-2: expressions of
	its bands (B8 is B8, not B8A), in the Vegetation theme, without unit, cited, and the water filter does not remove the
	aquatic vegetation that the WAVI measures."""
	monkeypatch.setitem(sensors._band_names, 'COPERNICUS/S2_SR_HARMONIZED',
	                    ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B9', 'B11', 'B12', 'SCL'])
	want = {'CLre': ('B8 / B5 - 1', 158, 20, {'B8': 'B8', 'B5': 'B5'}, ['gitelson2003', 'gitelson2005']),
	        'CLreB7': ('B7 / B5 - 1', 160, 20, {'B7': 'B7', 'B5': 'B5'}, ['gitelson2005', 'clevers2013']),
	        'WAVI': ('1.5 * (B8 - B2) / (B8 + B2 + 0.5)', 159, 10, {'B8': 'B8', 'B2': 'B2'}, ['villa2014'])}
	vegetation = next(t for t in catalog.THEMES if t['key'] == 'vegetation')['indices']
	for index, (ft, ref, m, bands, refs) in want.items():
		e = catalog.find(index, 'Sentinel-2')
		assert (e['ft'], e['f'], e['ref'], e['m'], e['unit'], e['scale']) == (ft, ft, ref, m, '[unitless]', 0.0001)
		assert e['references'] == refs and index in vegetation
		assert sensors.parse_formula(e) == ('expr', bands)
	assert 'WAVI' in sensors.MEASURES['water'] and 'CLre' not in sensors.MEASURES['water']


def test_app_has_the_catalog():
	"""The catalog of the Earth Engine app (gee/catalog.js, written by gee/build.py) is that of the package: run
	gee/build.py after changing catalog.json or catalog.py."""
	path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'gee', 'catalog.js')
	with open(path, encoding='utf-8') as f:
		text = f.read()
	app = {e['ref']: e for e in json.loads(text[text.index('{'):text.rindex('}') + 1])['variables']}
	entries = catalog.variables()
	assert sorted(app) == sorted(e['ref'] for e in entries), 'run gee/build.py: the app has other variables'
	for e in entries:
		for k, v in app[e['ref']].items():
			if k not in ('fk', 'fb'):  # the formula with the band names of Earth Engine
				assert v == e.get(k), f"run gee/build.py: {k} of {e['ref']} {e['index']} differs in the app"
	# the topographic wetness index: the kind of its formula and its two bands, and an image (not a collection)
	twi = app[148]
	assert (twi['fk'], twi['fb'], twi['image_asset']) == ('twi', ['elv', 'upa'], True), 'run gee/build.py'
	# the script of the app (monitoreo_app.js) carries that catalog, in ASCII
	with open(path.replace('catalog.js', 'monitoreo_app.js'), encoding='ascii') as f:
		script = f.read()
	assert ''.join(c if ord(c) < 128 else f'\\u{ord(c):04x}' for c in text) in script, 'run gee/build.py'


def test_rbr_in_the_catalog():
	# RBR (Silva-Cardoza et al. 2022): the NBR of B8A and B12 in Sentinel-2, NIR and SWIR2 in Landsat; it compares two
	# periods, so only burn_severity computes it
	s2, landsat = catalog.find('RBR', 'Sentinel-2'), catalog.find('rbr', 'landsat')
	assert (s2['ref'], s2['ft'], s2['m'], s2['col']) == (103, 'N(B8A,B12)', 20, 'COPERNICUS/S2_SR_HARMONIZED')
	assert (landsat['ref'], landsat['ft'], landsat['m']) == (104, 'N(nir,swir2)', 30)
	assert s2['two_periods'] and s2['vname_en'] == 'Relativized Burn Ratio' and '1.001' in s2['notes']['f']
	assert catalog.find('NBR', 'Sentinel-2')['ref'] == 102 and not catalog.find('NBR', 'Sentinel-2').get('two_periods')
	assert catalog.RBR_OFFSET == 1.001
	with pytest.raises(ValueError, match="burn_severity and index 'RBR'"):
		services.make_spec('RBR', 'Sentinel-2', '2021-07-15', '2021-08-31')
	assert services.make_spec('RBR', 'Sentinel-2', '2021-07-15', '2021-08-31', two_periods=True)['index'] == 'RBR'
	rows = services.list_variables(text='RBR')
	assert [r['ref'] for r in rows] == [103, 104] and all(r['two_periods'] for r in rows)
	assert 'two_periods' not in services.list_variables(text='NDVI')[0]
	with pytest.raises(ValueError, match='unknown burn index: use dNBR, RBR or RdNBR'):
		services.burn_severity({'bbox': [0, 0, 1, 1]}, index='NDVI')


def test_scf_in_the_catalog():
	# SCF: snow cover frequency of Landsat, from the bands of its NDSI; each image is 100 (snow) or 0, and its only
	# metric is the mean (the % of the clear observations with snow)
	e = catalog.find('scf', 'landsat')
	assert (e['ref'], e['col'], e['m'], e['unit'], e['minp'], e['maxp']) == (105, 'LANDSAT', 30, '[%]', 0, 100)
	assert e['vname_en'] == 'Snow cover frequency' and e['metric'] == 'mean' and e['scale'] == 2.75e-05
	assert sensors.is_scf(e) and not sensors.is_scf(catalog.find('NDSI', 'Landsat'))
	assert sensors.parse_formula(e) == ('scf', ['green', 'nir', 'swir1'])
	assert catalog.find('NDSI', 'Landsat')['unit'] == '[unitless]'  # the entry it copies is unchanged
	assert catalog.find('SCF', 'Sentinel-2')['ref'] == 156  # its own entry (see the test of the SCF of Sentinel-2)
	# fixed filters: always clouds and water, whatever the quality; never snow (what it measures) nor aerosols
	fixed = {'clouds': True, 'water': True, 'snow': False, 'aerosols': False}
	assert sensors.filters(e) == fixed and sensors.fixed_filters(e) == ['clouds', 'water']
	assert sensors.filters(e, {'clouds': False, 'water': 'auto', 'snow': True, 'aerosols': True}) == fixed
	assert sensors.conflicts(e) == [] and sensors.fixed_filters(catalog.find('NDSI', 'Landsat')) is None
	assert sensors.filters(catalog.find('NDSI', 'Landsat'), {'water': False})['water'] is False  # the others: free
	assert sensors.SCF['ndsi'] == 0.35 and sensors.SCF['toa_green'] == 0.08 and sensors.SCF['min_elevation'] == 1500
	assert set(sensors.SCF_TOA) == {c for c, _, _ in sensors.LANDSAT} | {'COPERNICUS/S2_SR_HARMONIZED'}
	# the mean, also in maps (whose default is the median); between years, any
	spec = services.make_spec('SCF', 'Landsat', '2020-10-01', '2021-05-31', metric='mean')
	assert spec['metric'] == 'mean' and spec['name'] == 'SCF_L_mean'
	for metric in ('median', 'max', ['mean', 'p95']):
		with pytest.raises(ValueError, match="only takes the metric 'mean'"):
			variable.specs({'index': 'SCF', 'sensor': 'Landsat', 'metric': metric, 'period': ['2020-10-01', '2021-05-31']})
	with pytest.raises(ValueError, match="only takes the metric 'mean'"):
		services.map_layer({'bbox': [-3.4, 37.0, -3.3, 37.1]}, 'SCF', 'Landsat', '2020-10-01', '2021-05-31')
	spec = services.make_spec('SCF', 'Landsat', '2000-01-01', '2020-12-31', temporal='annual', interannual='median',
	                          season=['10-01', '05-31'])
	assert spec['interannual'] == 'median'
	d = services.describe_variable('SCF', 'Landsat')
	assert d['metric'] == 'mean' and d['measures'] == ['snow'] and d['unit'] == '[%]' and 'hillShadow' in d['notes']['ft']
	assert d['fixed_filters'] == ['clouds', 'water'] and d['pixel_filters'] == fixed
	assert [r['ref'] for r in services.list_variables(text='snow cover frequency')] == [105, 151, 152, 156]
	assert services.list_variables(text='snow cover frequency')[0]['fixed_filters'] == ['clouds', 'water']
	assert 'fixed_filters' not in services.describe_variable('NDSI', 'Landsat')
	# the title of the y axis of its charts; the other variables keep their unit
	assert e['axis'] == 'Snow Cover Frequency (SCF)'
	assert services._ylabel(spec) == 'Snow Cover Frequency (SCF) [%]'
	assert services._ylabel(services.make_spec('NDSI', 'Landsat', '2020-10-01', '2021-05-31')) == '[unitless]'


def test_scf_of_modis_and_snow_cover_days_in_the_catalog():
	# the SCF of MODIS Terra and Aqua: from the daily snow product, the threshold of that of Landsat, its fixed filters
	for ref, col in ((151, 'MODIS/061/MOD10A1'), (152, 'MODIS/061/MYD10A1')):
		e = catalog.find(None, ref=ref)
		assert (e['index'], e['sensor'], e['col'], e['m'], e['unit'], e['metric']) == ('SCF', 'Modis', col, 500, '[%]',
		                                                                              'mean')
		assert sensors.is_scf(e) and sensors.parse_formula(e) == ('scf', ['NDSI_Snow_Cover'])  # no Earth Engine
		assert sensors.fixed_filters(e) == ['clouds', 'water'] and 'NDSI_Snow_Cover >= 35' in e['notes']['ft']
		assert 'hillShadow' not in e['notes']['ft'] and e['references'] == ['hall1995', 'riggs2017', 'hammond2018']
		# no rule of the shadow of the relief: its NDSI (TOA, without thresholds of brightness) sees the snow there, as
		# checked against Landsat (98.4 % of its snow in the shadow and in the sun)
		assert 'needs no rule of the shadow' in e['notes']['ft'] and '98.4 %' in e['notes']['ft']
	assert catalog.find('SCF', 'Modis')['ref'] == 151 and catalog.find('SCF', 'Modis', 'MODIS/061/MYD10A1')['ref'] == 152
	assert catalog.find('NDSI', 'Modis')['unit'] == '[unitless]'  # the entry they copy is unchanged
	# the snow cover days: the images of the SCF of each sensor, the only metric days, in days (UDUNITS day)
	for ref, sensor, base in ((153, 'Landsat', 105), (154, 'Modis', 151), (155, 'Modis', 152)):
		e, scf = catalog.find(None, ref=ref), catalog.find(None, ref=base)
		assert (e['index'], e['sensor'], e['col'], e['m']) == ('SCD', sensor, scf['col'], scf['m'])
		assert (e['unit'], e['metric'], e['axis'], e['theme']) == ('[days]', 'days', 'Snow Cover Days (SCD)', 'snow')
		assert e['ft'] == scf['ft'] and sensors.parse_formula(e) == sensors.parse_formula(scf)
		assert sensors.fixed_filters(e) == ['clouds', 'water'] and 'SCD' in sensors.MEASURES['snow']
	assert catalog.udunits('[days]') == 'day'
	assert [t for t in catalog.THEMES if t['key'] == 'snow'][0]['indices'] == ['NDSI', 'SCF', 'SCD', 'SMOD']
	# the metric days: only that of the snow cover days, not between the years, nor for the other variables
	spec = services.make_spec('SCD', 'Modis', '2021-10-01', '2022-05-31', metric='days')
	assert spec['metric'] == 'days' and spec['name'] == 'SCD_MODIS_days'
	assert services._ylabel(spec) == 'Snow Cover Days (SCD) [days]' and services._unit(spec) == '[days]'
	spec = services.make_spec('SCD', 'Landsat', '2000-10-01', '2020-05-31', metric='days', temporal='annual',
	                          interannual='median', season=['10-01', '05-31'])
	assert spec['interannual'] == 'median'
	with pytest.raises(ValueError, match="only takes the metric 'days'"):
		services.make_spec('SCD', 'Landsat', '2021-10-01', '2022-05-31', metric='mean')
	with pytest.raises(ValueError, match="only takes the metric 'days'"):
		services.map_layer({'bbox': [-3.4, 37.0, -3.3, 37.1]}, 'SCD', 'Modis', '2021-10-01', '2022-05-31')
	with pytest.raises(ValueError, match="'days' is not a metric between the years"):
		services.make_spec('SCD', 'Modis', '2010-10-01', '2020-05-31', metric='days', temporal='annual', interannual='days')
	for var, sensor in (('NDVI', 'Landsat'), ('SCF', 'Modis')):
		with pytest.raises(ValueError):
			services.make_spec(var, sensor, '2021-10-01', '2022-05-31', metric='days')
	with pytest.raises(ValueError, match="the metric 'days' is that of the snow cover days"):
		services.make_spec(collection='IDAHO_EPSCOR/TERRACLIMATE', band='pr', start='2020-01-01', end='2020-12-31',
		                   metric='days')
	d = services.describe_variable('SCD', 'Landsat')
	assert d['metric'] == 'days' and d['measures'] == ['snow'] and d['fixed_filters'] == ['clouds', 'water']
	assert [r['ref'] for r in services.list_variables(text='snow cover days')] == [153, 154, 155, 157]
	assert catalog.unit_of('[days]', 'days') == '[days]'


def test_snow_melt_out_day_in_the_catalog():
	# the images of the SCF of each sensor (its rules, shadows of the relief and fixed filters), the only metric melt
	for ref, sensor, base in ((161, 'Landsat', 105), (162, 'Modis', 151), (163, 'Modis', 152), (164, 'Sentinel-2', 156)):
		e, scf = catalog.find(None, ref=ref), catalog.find(None, ref=base)
		assert (e['index'], e['sensor'], e['col'], e['m']) == ('SMOD', sensor, scf['col'], scf['m'])
		assert (e['unit'], e['metric'], e['axis'], e['theme']) == ('[day of year]', 'melt', 'Snow Melt-Out Day (SMOD)',
		                                                           'snow')
		assert e['ft'] == scf['ft'] and sensors.parse_formula(e) == sensors.parse_formula(scf) and sensors.is_scf(e)
		assert sensors.fixed_filters(e) == ['clouds', 'water'] and 'SMOD' in sensors.MEASURES['snow']
		assert e['f'].startswith(scf['f']) and 'first clear image without snow after the last one with snow' in e['f']
		assert ('barroudumont2025' if sensor != 'Modis' else 'dietz2012') in e['references']
		assert 'MODIS sees the snow in the shadow as in the sun and needs none' in e['notes']['ft']
	assert catalog.find('SMOD', 'Sentinel-2')['ref'] == 164 and catalog.find('SMOD', 'Landsat')['ref'] == 161
	assert catalog.udunits('[day of year]') == 'day' and catalog.unit_of('[day of year]', 'melt') == '[day of year]'
	# the metric melt: only that of the snow melt-out day, not between the years, nor for the other variables
	spec = services.make_spec('SMOD', 'Sentinel-2', '2018-01-01', '2024-12-31', metric='melt')
	assert spec['metric'] == 'melt' and spec['name'] == 'SMOD_S2_melt'
	assert spec['season'] == composite.MELT_SEASON == ['01-01', '08-31']  # the default season, in the record
	assert services._ylabel(spec) == 'Snow Melt-Out Day (SMOD) [day of year]'
	spec = services.make_spec('SMOD', 'Landsat', '1990-01-01', '2020-12-31', metric='melt', temporal='annual',
	                          interannual='median', season=['03-01', '08-31'])
	assert spec['interannual'] == 'median' and spec['season'] == ['03-01', '08-31']  # the season given
	with pytest.raises(ValueError, match="only takes the metric 'melt'"):
		services.make_spec('SMOD', 'Landsat', '2021-01-01', '2021-12-31', metric='mean')
	with pytest.raises(ValueError, match="only takes the metric 'melt'"):
		services.map_layer({'bbox': [-3.4, 37.0, -3.3, 37.1]}, 'SMOD', 'Modis', '2021-01-01', '2021-12-31')
	with pytest.raises(ValueError, match="'melt' is not a metric between the years"):
		services.make_spec('SMOD', 'Modis', '2010-01-01', '2020-12-31', metric='melt', temporal='annual',
		                   interannual='melt')
	with pytest.raises(ValueError, match="one per year"):  # not monthly nor 16-day
		services.make_spec('SMOD', 'Modis', '2010-01-01', '2020-12-31', metric='melt', temporal='monthly')
	for var, sensor in (('NDVI', 'Landsat'), ('SCF', 'Modis'), ('SCD', 'Sentinel-2')):
		with pytest.raises(ValueError):
			services.make_spec(var, sensor, '2021-01-01', '2021-12-31', metric='melt')
	with pytest.raises(ValueError, match="the metric 'melt' is that of the snow melt-out day"):
		services.make_spec(collection='IDAHO_EPSCOR/TERRACLIMATE', band='pr', start='2020-01-01', end='2020-12-31',
		                   metric='melt')
	with pytest.raises(ValueError, match="only takes the metric 'melt'"):  # nor the days of the snow cover days
		services.make_spec('SMOD', 'Landsat', '2021-01-01', '2021-12-31', metric='days')
	# one value per year: the steps of series, trends and animations shorter than a year are refused
	for step in ('monthly', '16-day', 'daily'):
		with pytest.raises(ValueError, match=f"use the step 'annual'.*not '{step}'"):
			composite.check_step('melt', step)
	composite.check_step('melt', 'annual')
	composite.check_step('melt', 'period')
	composite.check_step('mean', 'monthly')  # the other metrics: any step
	with pytest.raises(ValueError, match='one per year'):
		services.time_series({'bbox': [-3.4, 37.0, -3.3, 37.1]}, 'SMOD', 'Sentinel-2', '2018-01-01', '2020-12-31',
		                     step='monthly', metric='melt')
	assert composite.is_melt(' Melt ') and composite.is_only('days') and not composite.is_only('mean')
	composite.check_metric('melt')
	d = services.describe_variable('SMOD', 'Landsat')
	assert d['metric'] == 'melt' and d['measures'] == ['snow'] and d['fixed_filters'] == ['clouds', 'water']
	assert [r['ref'] for r in services.list_variables(text='snow melt-out day')] == [161, 162, 163, 164]
	assert report.STATS['melt'] == 'snow melt-out day'


def test_scf_and_snow_cover_days_of_sentinel2_in_the_catalog():
	# the rules of the SCF of Landsat on the bands of the NDSI of Sentinel-2 (entry 8), at the 20 m of its SWIR1
	for ref, index, unit, metric in ((156, 'SCF', '[%]', 'mean'), (157, 'SCD', '[days]', 'days')):
		e = catalog.find(None, ref=ref)
		assert (e['index'], e['sensor'], e['col'], e['m'], e['unit'], e['metric']) == (
			index, 'Sentinel-2', 'COPERNICUS/S2_SR_HARMONIZED', 20, unit, metric)
		assert sensors.is_scf(e) and sensors.parse_formula(e) == ('scf', ['B3', 'B8', 'B11'])  # no Earth Engine
		assert sensors.fixed_filters(e) == ['clouds', 'water'] and e['theme'] == 'snow'
		assert e['references'] == ['hall1995', 'gascoin2019'] and catalog.find(index, 'Sentinel-2')['ref'] == ref
	notes = catalog.find(None, ref=156)['notes']['ft']
	assert 'Cloud Score+' in notes and 'hillShadow' in notes and 'Level-1C' in notes
	ndsi = catalog.find('NDSI', 'Sentinel-2')  # the entry they copy is unchanged
	assert (ndsi['ref'], ndsi['m'], ndsi['ft'], ndsi['unit']) == (8, 20, 'N(B3, B11)', '[unitless]')
	# the TOA reflectance of the same scene (Level-1C, its raw values x 0.0001), the clouds of Cloud Score+ always
	assert sensors.SCF_TOA['COPERNICUS/S2_SR_HARMONIZED'] == ('COPERNICUS/S2_HARMONIZED', ['B3', 'B11'])
	assert sensors.SCF_TOA_SCALE == {'COPERNICUS/S2_HARMONIZED': 0.0001} and sensors.SCF['cloud_score'] == 0.6
	assert services.make_spec('SCF', 'Sentinel-2', '2021-10-01', '2022-05-31', metric='mean')['name'] == 'SCF_S2_mean'
	assert services.make_spec('SCD', 'Sentinel-2', '2021-10-01', '2022-05-31', metric='days')['name'] == 'SCD_S2_days'
	with pytest.raises(ValueError, match="only takes the metric 'days'"):
		services.make_spec('SCD', 'Sentinel-2', '2021-10-01', '2022-05-31', metric='median')
	d = services.describe_variable('SCF', 'Sentinel-2')
	assert d['metric'] == 'mean' and d['fixed_filters'] == ['clouds', 'water']


def test_the_spans_of_the_snow_cover_days():
	# with temporal 'period', the snow cover days are the mean of those of each season, or of each 12 months from the
	# first day of the period without one: a season or a year is one span (its days), a long period its years
	d = dt.date
	assert composite.spans(['2021-10-01', '2022-05-31']) == [(d(2021, 10, 1), d(2022, 6, 1))]
	assert composite.spans(['2010-01-01', '2020-12-31'])[1] == (d(2011, 1, 1), d(2012, 1, 1))
	assert len(composite.spans(['2010-01-01', '2020-12-31'])) == 11
	assert composite.spans(['2010-01-01', '2011-06-30']) == [(d(2010, 1, 1), d(2011, 1, 1)), (d(2011, 1, 1), d(2011, 7, 1))]
	assert composite.spans(['2024-02-29', '2025-03-15'])[0] == (d(2024, 2, 29), d(2025, 2, 28))  # no 29 Feb in 2025
	assert composite.spans(['2010-10-01', '2013-05-31'], ['10-01', '05-31']) == [
		(d(2010, 10, 1), d(2011, 6, 1)), (d(2011, 10, 1), d(2012, 6, 1)), (d(2012, 10, 1), d(2013, 6, 1))]
	assert composite.is_days('Days') and not composite.is_days('mean') and not composite.is_days(None)
	composite.check_metric('days')
	with pytest.raises(ValueError, match='true colour'):
		composite.check_rgb_metric('days')


def test_the_snow_cover_days_sum_the_months(monkeypatch):
	# composite.days: the mean of the images of each month / 100 x its days, summed; a month without images takes the
	# mean of the others (weighted by their days): with stand-ins of the images of Earth Engine
	months = []

	class Image:
		def __init__(self, v, n=None):
			self.v, self.n = v, n  # v: the value (None: masked), n: the days of the month

		def multiply(self, k):
			return Image(None if self.v is None else self.v * k, self.n)

		def divide(self, other):
			return Image(None if self.v is None or not other.v else self.v / other.v)

		def mask(self):
			return Image(0 if self.v is None else 1)

		def updateMask(self, m):
			return Image(self.v if m.v not in (0, None, False) else None, self.n)

		def gt(self, k):
			return Image(self.v is not None and self.v > k)

		def toFloat(self):
			return self

		def rename(self, name):
			return self

	class Collection:
		def __init__(self, images):
			self.images = images

		def filterDate(self, a, b):
			months.append((a, b))
			return {'2022-01-01': 80, '2022-02-01': None, '2022-03-01': 20}[a]  # February: no image

		def sum(self):
			vals = [i.v for i in self.images if i.v is not None]
			return Image(sum(vals) if vals else None)

	monkeypatch.setattr(composite, '_reduce', lambda col, metric: Image(col))
	monkeypatch.setattr(composite, 'ee', types.SimpleNamespace(
		Image=types.SimpleNamespace(constant=lambda n: Image(n)),
		ImageCollection=types.SimpleNamespace(fromImages=Collection)))
	out = composite.days(Collection([]), '2022-01-01', '2022-04-01')
	assert months == [('2022-01-01', '2022-02-01'), ('2022-02-01', '2022-03-01'), ('2022-03-01', '2022-04-01')]
	# January 80 % of 31 days and March 20 % of 31: 24.8 + 6.2 = 31 days in 62 days with images, so February takes
	# their mean (50 %): 31 / 62 x 90 days = 45 days
	assert out.v == pytest.approx(45.0)


def test_unit_of_the_sums():
	"""The sum of a rate per month or per day (the annual precipitation) is a total in mm, in the results and in the
	metadata of the files; the other metrics keep the unit of the catalog."""
	from monitoreo import catalog, services, variable
	assert catalog.unit_of('[mm/month]', 'sum') == '[mm]'
	assert catalog.unit_of('[mm/day]', 'sum') == '[mm]'
	assert catalog.unit_of('[mm/month]', 'mean') == '[mm/month]'
	assert catalog.unit_of('[°C]', 'sum') == '[°C]'
	spec = services.make_spec('PRECIP', 'TerraClimate', '2020-01-01', '2020-12-31', metric='sum')
	assert services._unit(spec) == '[mm]'
	assert variable.describe(spec)['udunits'] == 'mm'
	spec = services.make_spec('PRECIP', 'TerraClimate', '2020-01-01', '2020-12-31')
	assert services._unit(spec) == '[mm/month]'
	# the data of Earth Engine by their ID (in UDUNITS): also per the days of each image (CHIRPS PENTAD, 8-day
	# products), written '/N days' too, and per day as 'd-1'; per hour, a rate whose sum is not a total
	for unit, total in (('mm month-1', 'mm'), ('mm day-1', 'mm'), ('mm d-1', 'mm'), ('mm (5 day)-1', 'mm'),
	                    ('kg m-2 (8 day)-1', 'kg m-2'), ('mm/d', 'mm'), ('mm/8 days', 'mm'), ('J m-2 day-1', 'J m-2')):
		assert catalog.unit_of(unit, 'sum') == catalog.unit_of(unit, 'SUM') == total, unit
		assert catalog.unit_of(unit, 'max') == unit
	assert catalog.unit_of('mm h-1', 'sum') == 'mm h-1' and catalog.unit_of('kg m-2 s-1', 'sum') == 'kg m-2 s-1'
	# the units of the catalog keep their own: its ET (a total of 8 days) and LE are as they were
	assert catalog.unit_of('[kg/m²/8 days]', 'sum') == '[kg/m²/8 days]' and catalog.unit_of('[J/m²/day]', 'sum') == \
		'[J/m²]'
	spec = services.make_spec(collection='UCSB-CHG/CHIRPS/PENTAD', band='precipitation', start='2020-01-01',
	                          end='2020-12-31', metric='sum', unit='mm/pentad')  # as describe_asset gives it
	assert spec['unit'] == 'mm (5 day)-1' and services._unit(spec) == 'mm' and variable.describe(spec)['udunits'] == 'mm'
	assert catalog.udunits(services._unit(spec), per_year=True) == 'mm year-1'  # the trends of the annual totals


def test_cloud_frequency_and_climate_in_the_catalog():
	# cloud frequency (CF): % of the observations with clouds, of MODIS Terra and Aqua, Sentinel-2 and Landsat; its
	# only metric is the mean and it has no pixel filters (clouds are what it measures)
	cfs = [e for e in catalog.variables() if e['index'] == 'CF']
	assert [(e['ref'], e['sensor'], e['col']) for e in cfs] == [
		(108, 'Modis', 'MODIS/061/MOD09GA'), (109, 'Modis', 'MODIS/061/MYD09GA'),
		(110, 'Sentinel-2', 'COPERNICUS/S2_SR_HARMONIZED'), (111, 'Landsat', 'LANDSAT')]
	for e in cfs:
		assert sensors.is_cf(e) and sensors.fixed_filters(e) == [] and e['metric'] == 'mean' and e['unit'] == '[%]'
		assert not any(sensors.filters(e, {'clouds': True}).values()) and 'wilson2016' in e['references']
		assert sensors.parse_formula(e)[0] == 'cf'
	assert sensors.parse_formula(cfs[2]) == ('cf', ['cs_cdf']) and catalog.find('cf', 'modis')['ref'] == 108
	with pytest.raises(ValueError, match="only takes the metric 'mean'"):
		services.make_spec('CF', 'Modis', '2023-01-01', '2023-12-31', metric='median')
	# climate: ERA5-Land, TerraClimate and CHIRPS (series), WorldClim (fixed layers), without pixel filters
	precip = {e['sensor']: e for e in catalog.variables() if e['index'] == 'PRECIP'}
	assert set(precip) == {'ERA5-Land', 'TerraClimate', 'CHIRPS'}
	assert precip['ERA5-Land']['scale'] == 1000 and precip['ERA5-Land']['unit'] == '[mm/month]'
	assert precip['CHIRPS']['unit'] == '[mm/day]' and precip['CHIRPS']['col'] == 'UCSB-CHC/CHIRPS/V3/DAILY_SAT'
	assert catalog.find('TMEAN', 'ERA5-Land')['offset'] == -273.15 and catalog.find('TMAX', 'TerraClimate')['scale'] == 0.1
	assert not any(sensors.filters(precip['ERA5-Land']).values())
	bio = [e for e in catalog.variables() if e['sensor'] == 'WorldClim']
	assert [e['index'] for e in bio] == [f'BIO{i:02d}' for i in range(1, 20)] and all(e['static'] for e in bio)
	assert catalog.find('BIO01', 'WorldClim')['scale'] == 0.1 and catalog.find('BIO04', 'WorldClim')['scale'] == 0.01
	assert catalog.find('BIO12', 'WorldClim')['unit'] == '[mm]'
	spec = services.make_spec('BIO01', 'WorldClim')
	assert variable.is_static(spec) and variable._static_spec(spec)['scale'] == 0.1
	assert all(catalog.udunits(e['unit']) for e in catalog.variables() if e['unit'] not in catalog.NO_UDUNITS)


def test_elevation_and_slope_in_the_catalog():
	# elevation and slope of the Copernicus DEM GLO-30: fixed layers, without dates (maps and their statistics only)
	for index, unit, terrain in (('ELEVATION', '[m]', None), ('SLOPE', '[°]', 'slope')):
		e = catalog.find(index, 'copernicus')
		assert (e['col'], e['band'], e['m'], e['unit'], e.get('terrain'), e['static']) == (
			'COPERNICUS/DEM/GLO30_2024_1', 'DEM', 30, unit, terrain, True)
		assert sensors.fixed_filters(e) == [] and not any(sensors.filters(e, {'clouds': True, 'water': True}).values())
		assert sensors.parse_formula(e) == ('static', ['DEM']) and e['type_en'] == 'Topography'
	# the topographic wetness index (148) and the categorical layers of RESOLVE (ECOREGION, BIOME), fixed layers too
	assert [e['ref'] for e in catalog.variables() if e.get('static')] == [106, 107, 184] + list(range(125, 144)) + [148, 149,
	                                                                                                          150]
	# no metric, period nor season: one spec, named without them
	spec = services.make_spec('SLOPE', 'Copernicus')
	assert spec['metric'] is None and spec['name'] == 'SLOPE_Copernicus' and variable.is_static(spec)
	assert services.make_spec('SLOPE', 'Copernicus', '2020-01-01', '2020-12-31', metric='p95')['name'] == 'SLOPE_Copernicus'
	assert services._title(services.make_spec('ELEVATION', 'Copernicus', '2020-01-01', '2020-12-31')) == 'ELEVATION Copernicus'
	assert services._named(spec, 'median') == 'SLOPE Copernicus' and services._ylabel(spec) == '[°]'
	assert services._file_stem('SLOPE', 'Copernicus', 'median', None, None, {}) == 'SLOPE_Copernicus'
	ndvi = services.make_spec('NDVI', 'Sentinel-2', '2020-01-01', '2020-12-31')
	assert not variable.is_static(ndvi) and services._named(ndvi, 'median').endswith('(median)')
	# no time series, trends or comparisons, with an error before any call to Earth Engine
	region = {'bbox': [-3.4, 37.0, -3.3, 37.1]}
	with pytest.raises(ValueError, match='ELEVATION .Copernicus. is a fixed layer, without dates'):
		services.time_series(region, 'ELEVATION', 'Copernicus', '2020-01-01', '2020-12-31')
	with pytest.raises(ValueError, match='fixed layer, without dates.* no comparisons'):
		services.compare_series(region, 'SLOPE', 'Copernicus', '2020-01-01', '2020-12-31', '2021-01-01', '2021-12-31')
	with pytest.raises(ValueError, match='fixed layer, without dates'):
		variable.collection(spec, None, 30)
	d = services.describe_variable('SLOPE', 'Copernicus')
	assert d['static'] and d['fixed_filters'] == [] and d['group'] == 'Topography' and 'degrees' in d['notes']['ft']
	assert [(r['variable'], r['static']) for r in services.list_variables(sensor='Copernicus')] == [
		('ELEVATION', True), ('SLOPE', True), ('ASPECT', True)]
	assert 'static' not in services.describe_variable('NDVI', 'Sentinel-2')


def test_twi_in_the_catalog():
	# the topographic wetness index (TWI) of MERIT Hydro: a fixed layer, without dates, of the theme Terrain, computed
	# from two bands of an image (formula TWI(elv,upa)), not from one band as the other fixed layers
	e = catalog.find('TWI', 'MERIT Hydro')
	assert (e['ref'], e['col'], e['band'], e['m'], e['unit'], e['static'], e['image_asset']) == (
		148, 'MERIT/Hydro/v1_0_1', 'elv', 90, '[unitless]', True, True)
	assert (e['tr'], e['scale'], e['offset'], e['large_areas'], e['type'], e['type_en']) == (
		'fixed', 1, 0, True, 'Topografía', 'Topography')
	assert (e['vname'], e['vname_en'], e['minp'], e['maxp'], e['pm']) == (
		'Índice topográfico de humedad', 'Topographic wetness index', 4, 20, catalog.SOIL_PALETTE)
	assert e['dr'] == 'fixed layer, without dates (MERIT Hydro v1.0.1, from MERIT DEM)' and e['pg']
	assert e.get('terrain') is None and e['theme'] == 'terrain' and catalog.udunits(e['unit']) == '1'
	assert e['ft'] == 'TWI(elv,upa)' and e['f'] == ('ln(a / max(tan(slope(elv)), 0.001)), '
	                                                'a = max(upa × 10^6, pixel area) / sqrt(pixel area)')
	# its own references and notes, not those of the Copernicus DEM of the template it copies
	assert e['references'] == ['beven1979', 'marthews2015', 'zevenbergen1987']
	note = e['notes']['ft']
	assert 'Copernicus' not in note and 'TanDEM-X' not in note
	for words in ('ln(a / tan β)', 'D8', '90 m', '3.5 to', 'between 5 and 15', 'mean of the logarithms',
	              'rivers and lakes are kept', 'CC BY-NC 4.0 or ODbL 1.0', 'A fixed layer, without dates'):
		assert words in note, words
	assert catalog.find('twi', 'merit hydro')['ref'] == catalog.find('TWI', 'MERITHydro')['ref'] == 148
	# the formula: the two bands as written (no need to ask Earth Engine for the band names of the image)
	assert sensors.is_twi(e) and not sensors.is_twi(catalog.find('SLOPE', 'Copernicus'))
	assert sensors.parse_formula(e) == ('twi', ['elv', 'upa'])
	assert sensors.TWI == {'area_scale': 1e6, 'min_tan_slope': 0.001}
	assert sensors.fixed_filters(e) == [] and sensors.rgb_of(e) is None
	assert not any(sensors.filters(e, {'clouds': True, 'water': True}).values())
	# not a terrain of the data by its ID (slope, aspect): only the catalog computes it
	assert 'twi' not in variable.TERRAIN
	# no metric, period nor season, as the other fixed layers
	spec = services.make_spec('TWI', 'MERIT Hydro', '2020-01-01', '2020-12-31', metric='p95')
	assert spec['metric'] is None and spec['name'] == 'TWI_MERIT_Hydro' and variable.is_static(spec)
	image = variable._static_spec(spec)
	assert (image['image'], image['band'], image['terrain'], image['formula']) == (
		'MERIT/Hydro/v1_0_1', 'elv', None, ('twi', ['elv', 'upa']))
	assert variable._types['MERIT/Hydro/v1_0_1'] == 'IMAGE'  # image_asset: no need to ask Earth Engine
	assert services._title(spec) == 'TWI MERIT Hydro' and services._named(spec, 'median') == 'TWI MERIT Hydro'
	assert services._ylabel(spec) == '[unitless]'
	assert services._file_stem('TWI', 'MERIT Hydro', 'median', None, None, {}) == 'TWI_MERIT Hydro'
	d = variable.describe(spec)
	assert (d['formula'], d['udunits'], d['native_resolution']) == ('TWI(elv,upa)', '1', 90)
	region = {'bbox': [-3.4, 37.0, -3.3, 37.1]}
	with pytest.raises(ValueError, match='TWI .MERIT Hydro. is a fixed layer, without dates'):
		services.time_series(region, 'TWI', 'MERIT Hydro', '2020-01-01', '2020-12-31')
	with pytest.raises(ValueError, match='fixed layer, without dates.* no comparisons'):
		services.compare_series(region, 'TWI', 'MERIT Hydro', '2020-01-01', '2020-12-31', '2021-01-01', '2021-12-31')
	d = services.describe_variable('TWI', 'MERIT Hydro')
	assert d['static'] and d['fixed_filters'] == [] and d['group'] == 'Topography' and 'D8' in d['notes']['ft']
	assert [(r['variable'], r['static'], r['theme']) for r in services.list_variables(sensor='MERIT Hydro')] == [
		('TWI', True, 'Terrain')]
	assert {r['variable'] for r in services.list_variables(theme='terrain')} == {'ELEVATION', 'SLOPE', 'ASPECT', 'TWI'}


def test_list_variables_compares_sensors_as_find():
	# the sensor of list_variables, as that of catalog.find: in any case and with or without its spaces
	for sensor in ('MERIT Hydro', 'merit hydro', 'MERITHydro', 'MERIT  Hydro'):
		assert [r['variable'] for r in services.list_variables(sensor=sensor)] == ['TWI'], sensor
		assert catalog.find('TWI', sensor)['ref'] == 148
	assert [r['variable'] for r in services.list_variables(sensor='Cop ernicus')] == ['ELEVATION', 'SLOPE', 'ASPECT']
	assert catalog.name_key('ERA5-Land') == catalog.name_key('era5-land') == 'era5-land'
	assert services.list_variables(sensor='MERIT-Hydro') == []  # a hyphen is not a space


def test_rbr_report():
	from monitoreo import publish, report
	args = {'sensor': 'Sentinel-2', 'start': '2021-07-15', 'end': '2021-08-31', 'other_start': '2021-09-20',
	        'other_end': '2021-10-31', 'index': 'RBR'}
	assert publish.fire_variable(args) == 'RBR' and publish.fire_variable(dict(args, index='dNBR')) == 'NBR'
	assert publish.default_title('burn_severity', args).startswith('Burn severity (RBR of Sentinel-2): before, 15 Jul')
	res = {'index': 'RBR', 'stats': [{'region': 'a', 'mean': 0.31, 'median': 0.29, 'p10': 0.02, 'p90': 0.6,
	                                  'min': -0.2, 'max': 0.9, 'ha': 812.4}]}
	cols, rows = report.item_table('burn_severity', res, args)
	assert cols[0] == 'RBR mean' and cols[-1] == 'Hectares' and rows == [['0.31', '0.29', '0.02', '0.6', '-0.2', '0.9',
	                                                                     '812.4']]
	facts = dict(report.item_facts('burn_severity', args, res))
	assert facts['Variable'].startswith('Relativized Burn Ratio') and '1.001' in facts['Method']
	assert 'USGS' in dict(report.item_facts('burn_severity', dict(args, index='dNBR'), {}))['Method']
	assert publish.BANDS['rbr'][0].startswith('RBR') and 'rbr' in publish.MAIN_BANDS


def test_list_and_describe():
	s2 = services.list_variables(sensor='Sentinel-2')
	assert s2 and all(v['sensor'] == 'Sentinel-2' for v in s2)
	assert services.list_variables(text='vegetación')
	d = services.describe_variable('NDSI', 'Modis')
	assert d['measures'] == ['snow'] and d['alternatives'] == ['MODIS/061/MYD10A1']


def test_windows_and_bins():
	w = composite.windows(['2018-01-01', '2019-12-31'])
	assert [x[0] for x in w] == [2018, 2019]
	w = composite.windows(['2018-03-15', '2020-06-30'], ['11-01', '02-29'])
	assert [(x[1].isoformat(), x[2].isoformat()) for x in w] == [('2018-11-01', '2019-03-01'), ('2019-11-01', '2020-03-01')]
	months = composite.bins((2020, dt.date(2020, 6, 1), dt.date(2020, 10, 1)), 'monthly')
	assert [m[0] for m in months] == [6, 7, 8, 9]
	spec = variable.specs({'index': 'NDVI', 'sensor': 'Sentinel-2', 'metric': 'mean', 'period': ['2020-01-01', '2020-12-31']})[0]
	assert len(timeseries.bins(spec, 'monthly')) == 12
	assert timeseries.bins(spec, 'annual') == [('2020-01-01', '2021-01-01')]
	assert len(timeseries.bins(spec, '16-day')) == 23


def test_metrics():
	for m in ('mean', 'median', 'p95', 'P2.5', 'std', 'count'):
		composite.check_metric(m)
	with pytest.raises(ValueError):
		composite.check_metric('foo')


def test_specs():
	s = variable.specs({'index': 'NDVI', 'sensor': 'Sentinel-2', 'metric': ['p95', 'p5'], 'period': ['2018-01-01', '2021-12-31']})
	assert [x['name'] for x in s] == ['NDVI_S2_p95', 'NDVI_S2_p5']
	assert s[0]['quality']['cloud_score'] == 0.6  # all quality options recorded
	with pytest.raises(ValueError):
		variable.specs({'index': 'NDVI', 'sensor': 'Sentinel-2', 'metric': 'mean', 'period': ['2018-01-01', '2021-12-31'],
		                'quality': {'clods': True}})
	spec = services.make_spec('LST', 'Modis', '2020-01-01', '2020-12-31', metric='max', temporal='annual')
	assert spec['temporal'] == 'annual' and variable.kind(spec) == 'catalog'
	spec = services.make_spec(image='COPERNICUS/DEM/GLO30_2024_1', band='DEM', terrain='slope')
	assert variable.kind(spec) == 'image'


def test_pixel_filters():
	ndsi = catalog.find('NDSI', 'Modis')
	assert sensors.filters(ndsi) == {'clouds': True, 'water': True, 'snow': False, 'aerosols': False}  # no QA band
	assert sensors.conflicts(catalog.find('NDSI', 'Sentinel-2')) == ['snow']
	assert sensors.filters(catalog.find('NDSI', 'Sentinel-2'), {'snow': 'auto'})['snow'] is False
	assert sensors.filters(catalog.find('NDVI', 'Landsat'))['aerosols'] is True
	assert sensors.filters(catalog.find('NDVI', 'Sentinel-2'))['aerosols'] is False


def test_grid():
	g = Grid.around('EPSG:32630', 10, 441310, 4078290, 455070, 4085990, margin=520)
	assert (g.width, g.height) == (1480, 874)
	assert g.extent == (440790.0, 4077770.0, 455590.0, 4086510.0)
	assert len(g.tiles(512)) == 6


def test_csv_climatology_chart(tmp_path):
	rows = [{'region': 'a', 'date': f'{y}-{m:02d}-01', 'value': m / 10, 'n_pixels': 5, 'n_images': 2}
	        for y in (2020, 2021) for m in range(1, 13)]
	rows[3]['value'] = None
	path = timeseries.write_csv(rows, tmp_path / 'ts.csv', {'variable': 'NDVI'})
	with open(path) as f:
		read = list(csv.DictReader(f))
	assert len(read) == 24 and read[3]['value'] == '' and read[0]['variable'] == 'NDVI'
	clim = timeseries.climatology(rows)
	assert len(clim) == 12 and clim[3]['n_years'] == 1
	png = charts.time_series_png(rows, tmp_path / 'ts.png', title='t', ylabel='u')
	assert png[:8] == b'\x89PNG\r\n\x1a\n' and (tmp_path / 'ts.png').exists()


def test_drive_folders(tmp_path):
	base = tmp_path / 'eHabitat_GEE'
	for d in (base, tmp_path / 'eHabitat_GEE (1)', tmp_path / 'eHabitat_GEE (2)', tmp_path / 'eHabitat_GEE old'):
		d.mkdir()
	(tmp_path / 'eHabitat_GEE (1)' / 'x_1.tif').write_bytes(b'')
	(tmp_path / 'eHabitat_GEE (2)' / 'x_1-0000000000-0000016384.tif').write_bytes(b'')
	(tmp_path / 'eHabitat_GEE old' / 'x_1.tif').write_bytes(b'')
	(base / 'x_10.tif').write_bytes(b'')
	assert len(drive.folders(str(base))) == 3
	found = [p.split('/')[-2:] for p in drive.find(str(base), 'x_1')]
	assert found == [['eHabitat_GEE (1)', 'x_1.tif'], ['eHabitat_GEE (2)', 'x_1-0000000000-0000016384.tif']]


def test_recipe(tmp_path):
	from monitoreo import recipe
	path = tmp_path / 'recipe.yaml'
	path.write_text("study: {resolution: 10}\nperiod: ['2018-01-01', '2021-12-31']\nvariables:\n"
	                "  - {index: NDVI, sensor: Sentinel-2, metric: [p95, p5]}\n"
	                "  - {name: slope, image: COPERNICUS/DEM/GLO30_2024_1, band: DEM, terrain: slope}\n")
	r = recipe.read(str(path))
	specs = recipe.expand(r)
	assert [s['file'] for s in specs] == ['1_NDVI_S2_p95.tif', '2_NDVI_S2_p5.tif', '3_slope.tif']
	assert specs[0]['period'] == ['2018-01-01', '2021-12-31'] and specs[0]['quality']['clouds'] is True
	with pytest.raises(ValueError, match='unknown keys'):
		recipe.read(dict(r, folder='gee'))
	assert recipe.read(dict(r, folder='gee'), extra={'folder'})
	with pytest.raises(ValueError, match='two variables'):
		recipe.expand(dict(r, variables=[{'name': 'a', 'image': 'X', 'band': 'b'}] * 2))
	with pytest.raises(ValueError, match='variable 1'):
		recipe.expand(dict(r, variables=[{'index': 'NDVI', 'sensor': 'Sentinel-2'}], period=None))
	warnings = []
	recipe.expand(dict(r, variables=[{'index': 'NDSI', 'sensor': 'Sentinel-2', 'metric': 'mean'}]), warn=warnings.append)
	assert len(warnings) == 1 and 'snow' in warnings[0]
	many = recipe.expand(dict(r, variables=[{'name': f'v{i}', 'image': 'X', 'band': 'b'} for i in range(10)]))
	assert many[0]['file'] == '01_v0.tif' and many[-1]['file'] == '10_v9.tif'
	# a unit left empty is not given (not dimensionless), as in the tools; the slope of a DEM is in degrees
	for unit in ('', ' '):
		spec, = recipe.expand(dict(r, variables=[{'collection': 'X/Y', 'band': 'b', 'metric': 'mean', 'unit': unit}]))
		assert 'unit' not in spec and 'unit' not in variable.describe(spec)
	assert specs[2]['unit'] == 'degree' and variable.describe(specs[2])['udunits'] == 'degree'
	assert variable.describe(specs[2])['variable'] == 'COPERNICUS/DEM/GLO30_2024_1 DEM slope'
	with pytest.raises(ValueError, match='is in degrees'):
		recipe.expand(dict(r, variables=[{'image': 'X/DEM', 'band': 'b', 'terrain': 'slope', 'unit': 'm'}]))
	with pytest.raises(ValueError, match='terrain is for an image'):
		recipe.expand(dict(r, variables=[{'collection': 'X/Y', 'band': 'b', 'metric': 'mean', 'terrain': 'slope'}]))
	with pytest.raises(ValueError, match='unknown terrain hillshade'):
		recipe.expand(dict(r, variables=[{'image': 'X/DEM', 'band': 'b', 'terrain': 'hillshade'}]))


def test_update(monkeypatch):
	from monitoreo import update
	calls, quiet = [], (lambda msg: None)
	new, old = 'b' * 40, 'a' * 40
	monkeypatch.setattr(update, '_pip', lambda *args: calls.append(args))
	assert update.local_copy()  # these tests run the clone (src)
	monkeypatch.setattr(update, 'local_copy', lambda: None)
	monkeypatch.setattr(update, 'latest', lambda: new)
	monkeypatch.setattr(update, 'installed', lambda: ('0.2.0', old, None))
	told = []  # installing() is called before pip
	assert update.ensure_latest('mcp,plot', log=quiet, installing=lambda: told.append(len(calls))) == 'updated'
	url = f'https://github.com/monitoreo-obsnev/monitoreo/archive/{new}.zip'
	assert calls == [('--force-reinstall', '--no-deps', f'monitoreo @ {url}'), (f'monitoreo[mcp,plot] @ {url}',)]
	assert told == [0]
	monkeypatch.setattr(update, 'installed', lambda: ('0.2.0', new, None))
	assert update.ensure_latest(log=quiet, installing=lambda: told.append(len(calls))) == 'current' and told == [0]
	monkeypatch.setattr(update, 'local_copy', lambda: '/clone/src/monitoreo')
	assert update.ensure_latest(log=quiet) == 'local' and len(calls) == 2

	def offline():
		raise OSError('no network')
	monkeypatch.setattr(update, 'latest', offline)
	assert update.ensure_latest(log=quiet) == 'offline'


def test_series_split_and_retry(monkeypatch):
	import ee
	calls = []

	def table(spec, regions, step, metric, stat, scale, steps, crs):
		calls.append(list(steps))

		class FC:
			def getInfo(self):
				if len(steps) > 2:
					raise ee.EEException('Too many concurrent aggregations.')
				return {'features': [{'properties': {'date': s}} for s in steps]}
		return FC()
	monkeypatch.setattr(timeseries, 'table', table)
	monkeypatch.setattr(timeseries.time, 'sleep', lambda s: None)
	rows = timeseries._fetch(None, None, 'monthly', 'mean', 'mean', 250, list('abcdefg'), 'EPSG:32630')
	assert [r['date'] for r in rows] == list('abcdefg') and calls[0] == list('abcdefg')

	def broken(*args):
		class FC:
			def getInfo(self):
				raise ee.EEException('Image.load: asset not found')
		return FC()
	monkeypatch.setattr(timeseries, 'table', broken)
	with pytest.raises(ee.EEException, match='not found'):  # not retried
		timeseries._fetch(None, None, 'monthly', 'mean', 'mean', 250, list('ab'), 'EPSG:32630')


def test_steps_without_value(monkeypatch):
	# Earth Engine leaves out the null properties: a year without images (Landsat in 2012) or without valid pixels
	# has no value, and the trend table of the QGIS plugin 0.2.3 failed with KeyError: 'value'
	def table(*args):
		class FC:
			def getInfo(self):
				return {'features': [{'properties': {'date': '2011-01-01', 'value': 0.4, 'n_pixels': 30, 'n_images': 10}},
				                     {'properties': {'date': '2012-01-01', 'n_images': 0}},
				                     {'properties': {'date': '2013-01-01', 'n_images': 14}},
				                     {'properties': {'date': '2014-01-01', 'value': 0.5, 'n_pixels': 32, 'n_images': 21}}]}
		return FC()
	monkeypatch.setattr(timeseries, 'table', table)
	rows = timeseries._fetch(None, None, 'annual', 'mean', 'mean', 30, ['2011'], 'EPSG:32630')
	assert [r['value'] for r in rows] == [0.4, None, None, 0.5] and rows[1]['n_pixels'] == 0
	for r in rows:
		r.update(region='zona', part=0, year=int(r['date'][:4]))
	t = trends.trend_rows(rows, 'annual')[0]
	assert t['n'] == 2 and t['slope'] == pytest.approx(0.1 / 3) and (t['first_year'], t['last_year']) == (2011, 2014)
	assert t['label'] == 'year' and trends.part_label('monthly', 7) == 'July'
	assert trends.part_label('16-day', 12) == 'days 177-192' and trends.part_label('16-day', 23) == 'days 353-366'


def test_about():
	from monitoreo import about
	for lang in ('en', 'es'):
		a = services.about(lang)
		assert a['description'].startswith('MonitorEO-OBSNEV') and 'PID2023-151939OB-I00' in a['acknowledgements']
		assert 'C-EXP-074-UGR23' in a['acknowledgements'] and 'PCI 2025-163175' in a['acknowledgements']
		assert len(a['logos']) == 3 and a['doi'] == about.DOI and f'https://doi.org/{about.DOI}' in a['citation']
	assert all(open(p, 'rb').read(4) in (b'\x89PNG', b'\xff\xd8\xff\xe0', b'\xff\xd8\xff\xe1') for p in about.LOGOS)
	assert 'NevadEO' in about.text('en') and 'PRESINMED' in about.text('es') and about.MANUAL in about.text('es')
	assert f'Cómo citar: {about.CITATION}' in about.text('es') and f'How to cite: {about.CITATION}' in about.text('en')


def test_burn_severity_classes():
	assert [c for c, _, _ in fire.SEVERITY] == [-2, -1, 0, 1, 2, 3, 4]
	assert fire.limits(1) == (0.1, 0.27) and fire.limits(-2) == (None, -0.25) and fire.limits(4) == (0.66, None)
	rows = fire.table([{'class': 1, 'sum': 12.5}, {'class': 3, 'sum': 2.0}], 'Teide')
	assert len(rows) == 7 and {r['class']: r['ha'] for r in rows}[1] == 12.5 and rows[0]['ha'] == 0.0
	# the colours of UN-SPIDER, the same in the app of Earth Engine (gee/core.js), and the names in English
	assert fire.COLOURS == {-2: '7a8737', -1: 'acbe4d', 0: '0ae042', 1: 'fff70b', 2: 'ffaf38', 3: 'ff641b', 4: 'a41fd6'}
	core = open(os.path.join(os.path.dirname(__file__), '..', 'gee', 'core.js'), encoding='utf-8').read()
	js = re.search(r"var SEVERITY_COLOURS = \[([^\]]+)\]", core).group(1)
	assert re.findall(r"'(\w+)'", js) == [fire.COLOURS[c] for c, _, _ in fire.SEVERITY]
	assert [n for _, _, n in fire.SEVERITY][0] == 'Enhanced regrowth, high' and fire.SEVERITY[-1][2] == 'High severity'


def test_shared_account(monkeypatch, tmp_path):
	# without a project, init connects with the shared account of MonitorEO: tokens of its broker, renewed when they
	# expire; it cannot export to Google Drive
	import time
	import types

	import requests
	for v in ('EE_PROJECT', 'GOOGLE_CLOUD_PROJECT', 'MONITOREO_BROKER'):
		monkeypatch.delenv(v, raising=False)
	monkeypatch.setattr(services, '_project', None)
	monkeypatch.setattr(services, '_shared', False)
	monkeypatch.setattr(services, 'USER_FILE', str(tmp_path / 'user_id'))
	monkeypatch.setattr(services, '_user', None)
	asked = []

	def get(url, timeout, headers):
		asked.append(url)
		return types.SimpleNamespace(status_code=200, headers={'Content-Type': 'application/json'},
		                             json=lambda: {'access_token': f'token{len(asked)}', 'project': 'shared-project',
		                                           'expires_at': time.time() + 3600})
	monkeypatch.setattr(requests, 'get', get)
	got = {}
	monkeypatch.setattr(services.ee, 'Initialize', lambda credentials=None, project=None: got.update(c=credentials,
	                                                                                                  p=project))
	assert services.init() == 'shared-project' and services.shared() and got['p'] == 'shared-project'
	user = services.user_id()
	assert asked == [services.BROKER + '/token?user=' + user] and got['c'].token == 'token1' and got['c'].valid
	assert services.ee.data.getWorkloadTag() == user  # what this user computes is tagged with their ID
	got['c'].refresh(None)
	assert got['c'].token == 'token2' and got['c'].valid
	assert services.init() == 'shared-project' and len(asked) == 2  # already connected
	with pytest.raises(RuntimeError, match='own Earth Engine account'):
		services.time_series_to_drive({'bbox': [0, 0, 1, 1]}, 'NDVI', 'Sentinel-2', '2020-01-01', '2020-02-01')
	with pytest.raises(RuntimeError, match='own Earth Engine account'):
		drive.export(None, None, 'name', 'MonitorEO', 'shared-project')

	monkeypatch.setattr(services.ee, 'Initialize', lambda project=None: got.update(c=None, p=project))
	assert services.init('mine') == 'mine' and not services.shared() and got['p'] == 'mine'
	assert services.ee.data.getWorkloadTag() == ''  # not with the user's own account
	services.need_own_account()  # nothing to stop with the user's own account

	monkeypatch.setattr(services, '_project', None)
	monkeypatch.setattr(requests, 'get', lambda url, timeout, headers: types.SimpleNamespace(
		status_code=429, headers={'Content-Type': 'application/json'}, json=lambda: {'error': 'too many requests'}))
	with pytest.raises(RuntimeError, match='shared account of MonitorEO: too many requests'):
		services.init()


class Response:
	def __init__(self, status, body):
		self.status_code, self.body = status, body
		self.headers = {'Content-Type': 'application/json'}

	def json(self):
		return self.body


def test_user_id(monkeypatch, tmp_path):
	# the anonymous ID of an installation: made at random once, kept in a file, valid as a workload tag of Earth Engine
	monkeypatch.setattr(services, 'USER_FILE', str(tmp_path / 'monitoreo' / 'user_id'))
	monkeypatch.setattr(services, '_user', None)
	user = services.user_id()
	assert re.fullmatch(r'mo-[0-9a-f]{16}', user) and services.ee.data._get_state().workload_tag.validate(user) == user
	monkeypatch.setattr(services, '_user', None)
	assert services.user_id() == user and (tmp_path / 'monitoreo' / 'user_id').read_text().strip() == user


def test_broker_limits_each_user(monkeypatch, tmp_path):
	# the broker (on this computer, with Cloud Monitoring faked) gives tokens only to users who have not spent their
	# research EECUs of the month, and tells each one what they have spent; the package asks for them with its ID
	import importlib.util
	import os
	import threading
	import urllib.parse
	from http.server import ThreadingHTTPServer
	monkeypatch.setenv('PUBLIC_SA', 'public@p.iam.gserviceaccount.com')
	monkeypatch.setenv('EE_PROJECT', 'shared-project')
	path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'broker', 'main.py')

	def load():
		spec = importlib.util.spec_from_file_location('broker_main', path)
		module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(module)
		return module
	broker = load()  # the Contributor tier: 25 EECU-hours a month for each user, 100 of the 1,000 kept for the app
	assert (broker.USER_LIMIT, broker.EECU_LIMIT, broker.PROJECT_RESERVE, broker.REQUIRE_USER) == (25, 1000, 100, True)
	monkeypatch.setenv('USER_LIMIT', '10')
	monkeypatch.setenv('EECU_LIMIT', '30')  # a reserve of 3: 12.5 EECU-hours left for the users of the shared account
	broker = load()
	assert broker.USER_LIMIT == 10 and broker.PROJECT_RESERVE == 3
	alice, bob = 'mo-' + 'a' * 16, 'mo-' + 'b' * 16
	monitoring = []

	counters = {}  # the quota counters of Earth Engine (consumer_quota): none yet

	def fake_json(url, data=None, headers=None):
		if url == broker.METADATA:
			return {'access_token': 'broker-token'}
		if 'consumer_quota' in urllib.parse.unquote_plus(url):
			metric = broker.QUOTA_LIMIT if broker.QUOTA_LIMIT in urllib.parse.unquote_plus(url) else broker.QUOTA_USAGE
			return {'timeSeries': [{'points': [{'interval': {'endTime': t}, 'value': {'int64Value': str(v)}}
			                                   for t, v in counters.get(metric, [])]}] if metric in counters else []}
		monitoring.append(url)
		seconds = {alice: 3 * 3600, bob: 10.5 * 3600}
		return {'timeSeries': [{'metric': {'labels': {'workload_tag': k}}, 'points': [{'value': {'doubleValue': v}}]}
		                       for k, v in seconds.items()] + [{'metric': {}, 'points': [{'value': {'int64Value': '3600'}}]}]}
	monkeypatch.setattr(broker, '_json', fake_json)
	monkeypatch.setattr(broker, 'token', lambda: {'access_token': 'shared-token', 'expires_at': 2e9,
	                                              'project': 'shared-project'})
	quota = {'status': ''}  # the header of Earth Engine about its restricted mode (none: not restricted)
	monkeypatch.setattr(broker, 'quota_status', lambda access_token, project: quota['status'])
	server = ThreadingHTTPServer(('127.0.0.1', 0), broker.Handler)
	threading.Thread(target=server.serve_forever, daemon=True).start()
	monkeypatch.setenv('MONITOREO_BROKER', f'http://127.0.0.1:{server.server_port}')
	try:
		with pytest.raises(services.BrokerError) as e:
			services._broker('/token')  # a version without the ID of its user
		assert e.value.code == 'user'
		assert services._broker('/token', user=alice)['access_token'] == 'shared-token'
		with pytest.raises(services.BrokerError) as e:
			services._broker('/token', user=bob)
		assert e.value.code == 'spent' and 'spent your research EECUs' in str(e.value)
		u = services._broker('/usage', user=alice)
		assert u['used_hours'] == 3 and u['limit_hours'] == 10 and u['project_used_hours'] == 14.5
		assert u['left_hours'] == 7 and u['project_left_hours'] == 12.5 and u['project_reserve_hours'] == 3
		monkeypatch.setattr(broker, 'EECU_LIMIT', 20.0)  # 2.5 left for all the users: what alice has left
		u = services._broker('/usage', user=alice)
		assert u['left_hours'] == 2.5 and u['project_left_hours'] == 2.5
		monkeypatch.setattr(broker, 'EECU_LIMIT', 17.0)  # nothing left for them but the reserve of the app
		with pytest.raises(services.BrokerError) as e:
			services._broker('/token', user=alice)
		assert e.value.code == 'project' and 'kept for the app of Earth Engine' in str(e.value)
		assert services._broker('/usage', user=alice)['left_hours'] == 0
		monkeypatch.setattr(broker, 'EECU_LIMIT', 30.0)
		assert services._broker('/usage', user=alice)['restricted'] is False

		# Earth Engine has put the project in restricted mode: nothing left, but tokens are still given (slowly)
		quota['status'] = 'parallelism_restricted=true'
		assert services._broker('/usage', user=alice)['restricted'] is False  # asked again after QUOTA_TTL seconds
		broker._quota['time'] = 0
		u = services._broker('/usage', user=alice)
		assert u['restricted'] is True and u['left_hours'] == 0 and u['project_left_hours'] == 0
		assert u['used_hours'] == 3 and u['project_used_hours'] == 14.5
		assert services._broker('/token', user=alice)['access_token'] == 'shared-token'

		def fails(access_token, project):
			raise OSError('no network')
		monkeypatch.setattr(broker, 'quota_status', fails)
		broker._quota['time'] = 0
		u = services._broker('/usage', user=alice)  # unknown: what the EECUs say
		assert u['restricted'] is None and u['left_hours'] == 7 and u['quota_reached'] is False
		assert 'project_quota_percent' not in u  # without the quota counters of Earth Engine
		assert len(monitoring) == 1
		monkeypatch.setattr(broker, 'quota_status', lambda access_token, project: '')

		# the quota counters of Earth Engine: its limit (40 EECU-hours, not EECU_LIMIT) and what it has counted, the
		# newest point (it counts more than the computations completed: 20 of 40, the users have 40 - 4 - 20 left)
		def ago(hours):  # an end time of a point of Cloud Monitoring, HOURS before now (this month, within 50 hours)
			return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)).strftime('%Y-%m-%dT%H:%M:%SZ')
		counters[broker.QUOTA_LIMIT] = [(ago(0.2), 40 * 3600)]
		counters[broker.QUOTA_USAGE] = [(ago(0.15), 30 * 3600), (ago(0.1), 20 * 3600)]
		newest = counters[broker.QUOTA_USAGE][-1][0]
		broker._usage['time'] = broker._quota['time'] = 0
		u = services._broker('/usage', user=alice)
		assert u['project_limit_hours'] == 40 and u['project_reserve_hours'] == 4 and u['project_used_hours'] == 14.5
		assert u['project_quota_used_hours'] == 20 and u['project_quota_percent'] == 50
		assert u['project_quota_time'] == newest
		assert u['project_left_hours'] == 21.5  # of the computations completed (40 - 4 - 14.5), not of the counter
		assert u['left_hours'] == 7 and u['restricted'] is False and u['quota_reached'] is False
		# Earth Engine has counted it all: restricted mode (without its header), nothing left, tokens still given
		counters[broker.QUOTA_USAGE].append((ago(0.05), 40 * 3600 + 100))
		broker._usage['time'] = broker._quota['time'] = 0
		u = services._broker('/usage', user=alice)
		assert u['quota_reached'] is True and u['restricted'] is True and u['left_hours'] == 0
		assert services._broker('/token', user=alice)['access_token'] == 'shared-token'
		# a project without a monthly limit (int64 max): EECU_LIMIT, and no count of Earth Engine
		counters[broker.QUOTA_LIMIT] = [(ago(0.2), 2 ** 63 - 1)]
		broker._usage['time'] = broker._quota['time'] = 0
		u = services._broker('/usage', user=alice)
		assert u['project_limit_hours'] == 30 and 'project_quota_percent' not in u and u['quota_reached'] is False and 'workload_tag' in monitoring[0]  # one query for every user, kept 5 minutes

		# the package: the research EECUs of the user of this installation, and no connection once they are spent
		for v in ('GOOGLE_CLOUD_PROJECT',):
			monkeypatch.delenv(v, raising=False)
		monkeypatch.delenv('EE_PROJECT')
		monkeypatch.setattr(services, '_project', None)
		monkeypatch.setattr(services, '_shared', False)
		monkeypatch.setattr(services, '_user', bob)
		with pytest.raises(RuntimeError, match='spent your research EECUs.*Meanwhile, use your own account'):
			services.init()
		assert services.project() is None
	finally:
		server.shutdown()


def test_broker_chat(monkeypatch):
	# /chat of the broker (on this computer, with Gemini faked): the model, the effort and the length of answer of the
	# broker whatever the request asks, its scope before the instructions, the key only towards Gemini, and the limits
	# of each address and of each user
	import importlib.util
	import io
	import threading
	import urllib.error
	import urllib.request
	from http.server import ThreadingHTTPServer
	monkeypatch.setenv('PUBLIC_SA', 'public@p.iam.gserviceaccount.com')
	monkeypatch.setenv('EE_PROJECT', 'shared-project')
	monkeypatch.setenv('CHAT_LIMIT', '3')
	monkeypatch.setenv('CHAT_USER_DAY', '2')
	monkeypatch.setenv('CHAT_MODELS', 'gemini-3.8-flash')
	monkeypatch.delenv('CHAT_CHOOSE', raising=False)
	monkeypatch.delenv('GEMINI_API_KEY', raising=False)
	path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'broker', 'main.py')
	spec = importlib.util.spec_from_file_location('broker_main', path)
	broker = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(broker)
	assert (broker.CHAT_MODELS, broker.CHAT_REASONING, broker.CHAT_LIMIT, broker.CHAT_USER_DAY) == (
		['gemini-3.8-flash'], 'low', 3, 2)
	sent = []

	class Answer(io.BytesIO):
		def __enter__(self):
			return self

		def __exit__(self, *a):
			return False

	def gemini(req, timeout=None):
		sent.append((req.full_url, dict(req.header_items()), json.loads(req.data)))
		return Answer(json.dumps({'choices': [{'message': {'role': 'assistant', 'content': 'Hola'}}],
		                          'usage': {'prompt_tokens': 10, 'completion_tokens': 2}}).encode())
	monkeypatch.setattr(urllib.request, 'urlopen', gemini)
	server = ThreadingHTTPServer(('127.0.0.1', 0), broker.Handler)
	threading.Thread(target=server.serve_forever, daemon=True).start()
	monkeypatch.setenv('MONITOREO_BROKER', f'http://127.0.0.1:{server.server_port}')
	alice, bob = 'mo-' + 'a' * 16, 'mo-' + 'b' * 16
	body = {'model': 'gemini-4-argon', 'max_tokens': 10 ** 6, 'stream': True, 'n': 4, 'temperature': 0.2,
	        'messages': [{'role': 'system', 'content': 'You are the assistant of MonitorEO.'},
	                     {'role': 'user', 'content': 'NDVI'}],
	        'tools': [{'type': 'function', 'function': {'name': 'time_series'}}]}
	try:
		with pytest.raises(services.BrokerError) as e:
			services._broker('/chat', body=body, user=alice)
		assert e.value.code == 'off'  # without the key of Gemini
		monkeypatch.setattr(broker, 'GEMINI_API_KEY', 'the-key')
		with pytest.raises(services.BrokerError) as e:
			services._broker('/chat', body=body)
		assert e.value.code == 'user'  # a version without the ID of its user
		answer = services._broker('/chat', body=body, user=alice)
		assert answer['choices'][0]['message']['content'] == 'Hola' and 'the-key' not in json.dumps(answer)
		url, headers, request = sent[0]
		assert url == broker.GEMINI and headers['Authorization'] == 'Bearer the-key'
		assert request['model'] == 'gemini-3.8-flash' and request['max_tokens'] == 8192 and request['stream'] is False
		assert request['reasoning_effort'] == 'low' and 'n' not in request and request['tools'] == body['tools']
		assert request['messages'][0]['content'] == broker.SCOPE + 'You are the assistant of MonitorEO.'
		assert request['messages'][1:] == body['messages'][1:]
		services._broker('/chat', body={'messages': [{'role': 'user', 'content': 'x'}]}, user=alice)
		assert sent[1][2]['messages'][0] == {'role': 'system', 'content': broker.SCOPE.strip()}  # its own one
		with pytest.raises(services.BrokerError) as e:
			services._broker('/chat', body=body, user=alice)
		assert e.value.code == 'day' and len(sent) == 2  # 2 requests a day for each user
		with pytest.raises(services.BrokerError) as e:
			services._broker('/chat', body=body, user=bob)
		assert e.value.code == 'address'  # and 3 an hour for each address
		monkeypatch.setattr(broker, 'CHAT_LIMIT', 100)
		monkeypatch.setattr(broker, 'CHAT_USER_DAY', 100)
		monkeypatch.setattr(broker, 'CHAT_MAX_BYTES', 100)
		with pytest.raises(services.BrokerError) as e:
			services._broker('/chat', body=body, user=bob)
		assert e.value.code == 'request' and len(sent) == 2  # too big: not sent to Gemini
		monkeypatch.setattr(broker, 'CHAT_MAX_BYTES', 2 ** 20)
		with pytest.raises(services.BrokerError) as e:
			services._broker('/chat', body={'messages': []}, user=bob)
		assert e.value.code == 'request'

		def refused(status, detail):
			def urlopen(req, timeout=None):
				raise urllib.error.HTTPError(req.full_url, status, 'error', {}, io.BytesIO(json.dumps(detail).encode()))
			return urlopen
		monkeypatch.setattr(urllib.request, 'urlopen', refused(429, {'error': {'message': 'quota'}}))
		with pytest.raises(services.BrokerError) as e:
			services._broker('/chat', body=body, user=bob)
		assert e.value.code == 'busy' and 'try again in a minute' in str(e.value)
		monkeypatch.setattr(urllib.request, 'urlopen', refused(400, [{'error': {'message': 'Invalid schema'}}]))
		with pytest.raises(services.BrokerError) as e:
			services._broker('/chat', body=body, user=bob)
		assert e.value.code == 'model' and str(e.value).endswith('did not take the request: Invalid schema')
	finally:
		server.shutdown()


def _broker_module(monkeypatch, **env):
	"""broker/main.py loaded with ENV (and the variables it needs)."""
	import importlib.util
	monkeypatch.setenv('PUBLIC_SA', 'public@p.iam.gserviceaccount.com')
	monkeypatch.setenv('EE_PROJECT', 'shared-project')
	for k in ('GEMINI_API_KEY', 'ANTHROPIC_API_KEY', 'ZAI_API_KEY', 'GLM_MODELS', 'CHAT_MODELS', 'CHAT_MODEL',
	          'CHAT_CHOOSE'):
		monkeypatch.delenv(k, raising=False)
	for k, v in env.items():
		monkeypatch.setenv(k, v)
	path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'broker', 'main.py')
	spec = importlib.util.spec_from_file_location('broker_main', path)
	broker = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(broker)
	return broker


def test_broker_gemini_schemas(monkeypatch):
	# the schemas of the tools as Gemini takes them: «X or null» as X, a region (an object without properties) as JSON
	# text, which the assistant decodes, and without titles, defaults nor additionalProperties; and only what Gemini gave
	# of the blocks of the messages
	broker = _broker_module(monkeypatch)
	tools = [{'type': 'function', 'function': {'name': 'time_series', 'description': 'Series.', 'parameters': {
		'type': 'object', 'title': 'Args', 'required': ['region', 'variable', 'collection'], 'properties': {
			'region': {'type': 'object', 'additionalProperties': True, 'title': 'Region'},
			'variable': {'type': 'string'},
			'season': {'anyOf': [{'type': 'array', 'items': {'type': 'string'}}, {'type': 'null'}], 'default': None},
			'metric': {'anyOf': [{'type': 'string', 'enum': ['mean', 'median']}, {'type': 'null'}], 'default': None,
			           'title': 'Metric', 'description': 'The statistic.'}}}}},
		{'type': 'function', 'function': {'name': 'list_variables', 'description': 'Variables.',
		                                  'parameters': {'type': 'object', 'properties': {}}}}]
	out = broker.gemini_tools(tools)
	params = out[0]['function']['parameters']
	assert params['properties']['region'] == {'type': 'string', 'description': 'A JSON object, written as text.'}
	assert params['properties']['season'] == {'type': 'array', 'items': {'type': 'string'}}
	assert params['properties']['metric'] == {'type': 'string', 'enum': ['mean', 'median'],
	                                          'description': 'The statistic.'}
	assert params['required'] == ['region', 'variable']
	assert 'parameters' not in out[1]['function']  # a tool without arguments
	text = json.dumps(out)
	assert '"title"' not in text and '"default"' not in text and 'additionalProperties' not in text and 'anyOf' not in text
	request = broker.gemini_request({'model': 'gemini-3.8-flash', 'max_tokens': 10, 'tools': tools, 'messages': [
		{'role': 'assistant', 'content': '', 'extra_content': {'anthropic': {'content': []}, 'google': {'s': 1}},
		 'tool_calls': [{'id': 'c', 'extra_content': {'anthropic': 1}, 'function': {'name': 'x', 'arguments': '{}'}}]},
		{'role': 'assistant', 'content': 'a', 'extra_content': {'anthropic': {'content': []}}}]})
	assert request['messages'][0]['extra_content'] == {'google': {'s': 1}}
	assert 'extra_content' not in request['messages'][0]['tool_calls'][0] and 'extra_content' not in request['messages'][1]
	assert request['stream'] is False and request['reasoning_effort'] == 'low' and request['tools'] == out


def test_broker_claude(monkeypatch):
	# Claude through /chat: the request of the assistant (in the form of OpenAI) as the Messages API takes it, with the
	# instructions and the conversation cached, the blocks that Claude gave back as they came, the answers of the tools
	# of a turn together, drop_block, the fallbacks where they exist and no temperature; and its answer in the form of
	# OpenAI, with its blocks to be sent back
	import threading
	from http.server import ThreadingHTTPServer
	broker = _broker_module(monkeypatch, CHAT_MODELS='gemini-3.8-flash,claude-sonnet-5-5,claude-haiku-5-5',
	                        CHAT_CHOOSE='1',
	                        GEMINI_API_KEY='g', ANTHROPIC_API_KEY='a')
	assert broker.CHAT_MODELS == ['gemini-3.8-flash', 'claude-sonnet-5-5', 'claude-haiku-5-5']
	called = []
	thinking = {'type': 'thinking', 'thinking': '', 'signature': 'sig1'}

	def claude_call(params):
		called.append(params)
		return {'model': params['model'], 'stop_reason': 'tool_use', 'content': [
			{'type': 'thinking', 'thinking': '', 'signature': 'sig2'}, {'type': 'text', 'text': 'Busco el área.'},
			{'type': 'tool_use', 'id': 'toolu_2', 'name': 'find_protected_areas', 'input': {'text': 'Doñana'}}],
			'usage': {'input_tokens': 50, 'cache_read_input_tokens': 7000, 'cache_creation_input_tokens': 300,
			          'output_tokens': 120},
			'input_transformations': [{'type': 'thinking_dropped', 'reason': 'prefix_binding_mismatch'}]}
	monkeypatch.setattr(broker, '_claude_call', claude_call)
	asked_gemini = []
	monkeypatch.setattr(broker, 'gemini', lambda request: asked_gemini.append(request['model']) or {
		'model': request['model'], 'choices': [{'message': {'role': 'assistant', 'content': 'Hola'}}]})
	server = ThreadingHTTPServer(('127.0.0.1', 0), broker.Handler)
	threading.Thread(target=server.serve_forever, daemon=True).start()
	monkeypatch.setenv('MONITOREO_BROKER', f'http://127.0.0.1:{server.server_port}')
	user = 'mo-' + 'd' * 16
	tools = [{'type': 'function', 'function': {'name': 'time_series', 'description': 'Series.', 'parameters': {
		'type': 'object', 'properties': {'region': {'type': 'object', 'additionalProperties': True}}}}},
		{'type': 'function', 'function': {'name': 'list_variables', 'description': 'Variables.'}}]
	earlier = [thinking, {'type': 'tool_use', 'id': 'toolu_1', 'name': 'time_series', 'input': {'variable': 'NDVI'}},
	           {'type': 'tool_use', 'id': 'toolu_9', 'name': 'list_variables', 'input': {}}]
	body = {'model': 'claude-sonnet-5-5', 'temperature': 0.2, 'tools': tools, 'messages': [
		{'role': 'system', 'content': 'You are the assistant of MonitorEO.'},
		{'role': 'user', 'content': 'NDVI'},
		{'role': 'assistant', 'content': 'shown text, fixed by the assistant',
		 'extra_content': {'anthropic': {'content': earlier}},
		 'tool_calls': [{'id': 'toolu_1', 'type': 'function', 'function': {'name': 'time_series', 'arguments': '{}'}}]},
		{'role': 'tool', 'tool_call_id': 'toolu_1', 'content': 'Done'},
		{'role': 'tool', 'tool_call_id': 'toolu_9', 'content': 'No answer.'},
		{'role': 'assistant', 'content': 'Hecho.'},
		{'role': 'user', 'content': 'Y en Doñana'}]}
	from monitoreo import services
	try:
		answer = services._broker('/chat', body=body, user=user)
		params = called[0]
		assert params['model'] == 'claude-sonnet-5-5' and params['max_tokens'] == 8192 and 'temperature' not in params
		assert params['system'] == [{'type': 'text', 'text': broker.SCOPE + 'You are the assistant of MonitorEO.',
		                             'cache_control': {'type': 'ephemeral'}}]
		assert params['cache_control'] == {'type': 'ephemeral'}  # and the conversation, with the automatic breakpoint
		assert params['thinking'] == {'type': 'adaptive', 'block_binding': {'prefix_mismatch_behavior': 'drop_block'}}
		assert params['betas'] == ['thinking-binding-controls-2026-08-01', 'server-side-fallback-2026-07-01']
		assert params['fallbacks'] == 'default' and params['output_config'] == {'effort': 'low'}
		assert params['tools'] == [{'name': 'time_series', 'description': 'Series.', 'input_schema': {
			'type': 'object', 'properties': {'region': {'type': 'object', 'additionalProperties': True}}}},
			{'name': 'list_variables', 'description': 'Variables.', 'input_schema': {'type': 'object', 'properties': {}}}]
		assert params['messages'] == [
			{'role': 'user', 'content': 'NDVI'},
			{'role': 'assistant', 'content': earlier},  # as Claude gave it, not the text shown
			{'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'toolu_1', 'content': 'Done'},
			                             {'type': 'tool_result', 'tool_use_id': 'toolu_9', 'content': 'No answer.'}]},
			{'role': 'assistant', 'content': [{'type': 'text', 'text': 'Hecho.'}]},  # a turn of another model
			{'role': 'user', 'content': 'Y en Doñana'}]
		message = answer['choices'][0]['message']
		assert answer['model'] == 'claude-sonnet-5-5' and message['content'] == 'Busco el área.'
		assert message['tool_calls'] == [{'id': 'toolu_2', 'type': 'function', 'function': {
			'name': 'find_protected_areas', 'arguments': '{"text": "Doñana"}'}}]
		assert message['extra_content']['anthropic']['content'][0]['signature'] == 'sig2'
		assert answer['usage'] == {'prompt_tokens': 7350, 'completion_tokens': 120, 'cache_read_tokens': 7000,
		                           'cache_write_tokens': 300} and 'dropped_thinking' not in answer
		services._broker('/chat', body={**body, 'model': 'claude-haiku-5-5'}, user=user)
		assert 'fallbacks' not in called[1] and called[1]['betas'] == ['thinking-binding-controls-2026-08-01']
		services._broker('/chat', body={**body, 'model': 'claude-opus-9'}, user=user)  # not one of CHAT_MODELS
		assert asked_gemini == ['gemini-3.8-flash'] and len(called) == 2  # the first one
	finally:
		server.shutdown()
	refused = broker.claude_answer({'model': 'claude-sonnet-5-5', 'stop_reason': 'refusal', 'content': []})
	assert refused['choices'][0]['message'] == {'role': 'assistant',
	                                           'content': 'The language model of MonitorEO declined this request.'}
	monkeypatch.setattr(broker, 'ANTHROPIC_API_KEY', '')
	with pytest.raises(broker.ChatError) as e:
		broker.chat(json.dumps({**body, 'model': 'claude-sonnet-5-5'}).encode(), '1.2.3.4', user)
	assert e.value.answer['code'] == 'off'  # without its key


def test_broker_without_credit(monkeypatch):
	# Claude Sonnet 5.5 answers, whatever model the request asks for (the users do not choose); only when the API of
	# Anthropic says that there is no credit does Gemini answer, for an hour, and then Claude is asked again
	broker = _broker_module(monkeypatch, GEMINI_API_KEY='g', ANTHROPIC_API_KEY='a')
	assert broker.CHAT_MODELS == ['claude-sonnet-5-5', 'gemini-3.8-flash'] and not broker.CHAT_CHOOSE
	asked, credit = [], {'left': True}

	def claude_call(params):
		asked.append(params['model'])
		if not credit['left']:
			raise broker.ChatError(503, 'credit', 'the language model of MonitorEO has no credit left')
		return {'model': params['model'], 'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': 'Hola'}]}

	def gemini(request):
		asked.append(request['model'])
		return {'model': request['model'], 'choices': [{'message': {'role': 'assistant', 'content': 'Hola'}}]}
	monkeypatch.setattr(broker, '_claude_call', claude_call)
	monkeypatch.setattr(broker, 'gemini', gemini)
	user = 'mo-' + 'f' * 16
	body = json.dumps({'model': 'gemini-3.8-flash', 'messages': [{'role': 'user', 'content': 'Hola'}]}).encode()
	assert broker.chat(body, '1.1.1.1', user)['model'] == 'claude-sonnet-5-5' and asked == ['claude-sonnet-5-5']
	credit['left'] = False
	assert broker.chat(body, '1.1.1.1', user)['model'] == 'gemini-3.8-flash'
	assert asked[1:] == ['claude-sonnet-5-5', 'gemini-3.8-flash']
	broker.chat(body, '1.1.1.1', user)
	assert asked[3:] == ['gemini-3.8-flash']  # Claude is not asked meanwhile
	broker._no_credit['claude-sonnet-5-5'] = 0  # an hour later
	credit['left'] = True
	assert broker.chat(body, '1.1.1.1', user)['model'] == 'claude-sonnet-5-5'

	def busy(params):
		raise broker.ChatError(503, 'busy', 'the language model of MonitorEO is busy: try again in a minute')
	monkeypatch.setattr(broker, '_claude_call', busy)
	with pytest.raises(broker.ChatError) as e:
		broker.chat(body, '1.1.1.1', user)
	assert e.value.answer['code'] == 'busy' and asked[-1] == 'claude-sonnet-5-5'  # only without credit, Gemini
	monkeypatch.setattr(broker, 'ANTHROPIC_API_KEY', '')
	assert broker.chat(body, '1.1.1.1', user)['model'] == 'gemini-3.8-flash'  # without the key of Claude


def test_broker_glm(monkeypatch):
	# the backup key of GLM of the assistant: a request that asks for a model of GLM gets it (the users do not choose the
	# other models), with the key of the secret towards Z.ai only, the messages with only their standard fields and
	# without thinking; if it is busy, the other free model; without the key of GLM, GLM is not available
	import io
	import urllib.error
	import urllib.request
	broker = _broker_module(monkeypatch, GEMINI_API_KEY='g', ZAI_API_KEY='z')
	assert broker.GLM_MODELS == ['glm-4.7-flash', 'glm-4.5-flash'] and broker.model_key('glm-4.5-flash') == 'z'
	sent, busy = [], set()

	class Answer(io.BytesIO):
		def __enter__(self):
			return self

		def __exit__(self, *a):
			return False

	def urlopen(req, timeout=None):
		request = json.loads(req.data)
		sent.append((req.full_url, dict(req.header_items()), request))
		if request['model'] in busy:
			raise urllib.error.HTTPError(req.full_url, 429, 'busy', {}, io.BytesIO(
				json.dumps({'error': {'code': '1305', 'message': 'overloaded'}}).encode()))
		return Answer(json.dumps({'model': request['model'], 'usage': {'prompt_tokens': 5, 'completion_tokens': 1},
		                          'choices': [{'message': {'role': 'assistant', 'content': 'Hola'}}]}).encode())
	monkeypatch.setattr(urllib.request, 'urlopen', urlopen)
	user = 'mo-' + 'e' * 16
	messages = [{'role': 'system', 'content': 'You are the assistant of MonitorEO.'},
	            {'role': 'user', 'content': 'NDVI'},
	            {'role': 'assistant', 'content': None, 'extra_content': {'anthropic': {'content': []}},
	             'tool_calls': [{'id': 'c1', 'type': 'function', 'extra_content': {'google': {}},
	                             'function': {'name': 'list_variables', 'arguments': '{}'}}]},
	            {'role': 'tool', 'tool_call_id': 'c1', 'content': 'NDVI…'}]
	body = json.dumps({'model': 'glm-4.5-flash', 'messages': messages, 'temperature': 0.2,
	                   'tools': [{'type': 'function', 'function': {'name': 'list_variables'}}]}).encode()
	assert broker.chat(body, '1.1.1.1', user)['model'] == 'glm-4.5-flash'
	url, headers, request = sent[0]
	assert url == broker.GLM and headers['Authorization'] == 'Bearer z' and 'g' not in headers['Authorization'][7:]
	assert request['thinking'] == {'type': 'disabled'} and request['max_tokens'] == broker.CHAT_MAX_TOKENS
	assert request['messages'][0]['content'] == broker.SCOPE + 'You are the assistant of MonitorEO.'
	assert request['messages'][2] == {'role': 'assistant', 'content': '', 'tool_calls': [
		{'id': 'c1', 'type': 'function', 'function': {'name': 'list_variables', 'arguments': '{}'}}]}
	assert request['messages'][3] == {'role': 'tool', 'content': 'NDVI…', 'tool_call_id': 'c1'}
	busy.add('glm-4.5-flash')  # busy: the other free model answers
	assert broker.chat(body, '1.1.1.1', user)['model'] == 'glm-4.7-flash'
	assert [r['model'] for _, _, r in sent[1:]] == ['glm-4.5-flash', 'glm-4.7-flash']
	busy.add('glm-4.7-flash')
	with pytest.raises(broker.ChatError) as e:
		broker.chat(body, '1.1.1.1', user)
	assert e.value.answer['code'] == 'busy' and 'GLM (Z.ai) is busy' in e.value.answer['error']
	monkeypatch.setattr(broker, 'ZAI_API_KEY', '')  # a broker without the key of GLM: no other model instead
	sent.clear()
	with pytest.raises(broker.ChatError) as e:
		broker.chat(body, '1.1.1.1', user)
	assert e.value.answer == {'code': 'off', 'error': 'GLM (Z.ai) is not available in MonitorEO'} and not sent
	assert broker.chat(body.replace(b'glm-4.5-flash', b'claude-x'), '1.1.1.1', user)['model'] == 'gemini-3.8-flash'


def test_quota_warning_in_the_cli_and_the_mcp_server(monkeypatch, capsys):
	"""After the commands that compute, the command line warns of the restricted mode of Earth Engine, and the MCP
	server puts it in the answers of its tools; nothing tells the EECUs spent (their count was not that of Earth
	Engine): no command eecu, no tool eecu_usage."""
	from monitoreo import cli
	monkeypatch.setattr(services, 'init', lambda project=None, shared=False, warn=True: 'p')
	monkeypatch.setattr(services, 'quota_warning', lambda once=False: 'Restricted mode')
	monkeypatch.setattr(services, 'find_protected_areas', lambda text, limit: [])
	cli.main(['parks', 'Sierra'])
	assert 'WARNING: Restricted mode' in capsys.readouterr().err  # after the commands that compute
	with pytest.raises(SystemExit):
		cli.main(['eecu'])
	assert not hasattr(services, 'eecu_usage') and not hasattr(services, 'eecu_warning')
	assert 'EECU_TIERS' not in dir(services) and 'monitoreo eecu' not in cli.__doc__

	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	assert not hasattr(mcp_server, 'eecu_usage')
	assert json.loads(mcp_server._quota_warning('{"a": 1}')) == {'a': 1, 'quota_warning': 'Restricted mode'}
	out = mcp_server._quota_warning(['{"a": 1}', 'image'])
	assert json.loads(out[0])['quota_warning'] == 'Restricted mode' and out[1] == 'image'
	assert mcp_server._quota_warning('[1, 2]') == '[1, 2]'  # only in objects
	monkeypatch.setattr(services, 'quota_warning', lambda once=False: None)
	assert mcp_server._quota_warning('{"a": 1}') == '{"a": 1}'


class _Google:
	"""A session of Google (AuthorizedSession) with the answers of the APIs that own_projects asks: ANSWERS
	{(url prefix, x-goog-user-project): (status, JSON)}; it keeps what it was asked."""

	def __init__(self, answers):
		self.answers, self.asked = answers, []

	def get(self, url, params=None, timeout=None, headers=None):
		project = (headers or {}).get('x-goog-user-project')
		self.asked.append((url, project))
		for (prefix, quota), (status, body) in self.answers.items():
			if url.startswith(prefix) and quota == project:
				return types.SimpleNamespace(status_code=status, json=lambda body=body: body)
		return types.SimpleNamespace(status_code=403, json=lambda: {'error': {'message': 'not enabled'}})


def test_own_projects(monkeypatch, tmp_path):
	"""own_projects: the candidates (the one known, EE_PROJECT, earthengine set_project, the Google Cloud CLI,
	ee-<user> of the e-mail, BigQuery and, through a project that has it, Resource Manager), only those registered in
	Earth Engine (the configuration of each one, asked with its quota), in that order; without a sign-in, an error."""
	import google.auth.transport.requests
	credentials = tmp_path / 'credentials'
	monkeypatch.setattr(services.ee.oauth, 'get_credentials_path', lambda: str(credentials))
	monkeypatch.setattr(services.ee.data, 'get_persistent_credentials', lambda: object())
	for v in ('EE_PROJECT', 'GOOGLE_CLOUD_PROJECT'):
		monkeypatch.delenv(v, raising=False)
	gcloud = tmp_path / 'gcloud'
	(gcloud / 'configurations').mkdir(parents=True)
	(gcloud / 'active_config').write_text('work')
	(gcloud / 'configurations' / 'config_work').write_text('[core]\nproject = cli-project\naccount = x@y.z\n')
	monkeypatch.setenv('CLOUDSDK_CONFIG', str(gcloud))
	with pytest.raises(RuntimeError, match='sign in'):
		services.own_projects()
	credentials.write_text(json.dumps({'refresh_token': 'r', 'project': 'set-project'}))
	ee_ = 'https://earthengine.googleapis.com/v1/projects/'
	registered = {'cli-project': 'REGISTERED_NOT_COMMERCIALLY', 'ee-anaperez': 'REGISTERED_NOT_COMMERCIALLY',
	              'bq-project': 'REGISTERED_COMMERCIALLY', 'all-project': 'REGISTERED_NOT_COMMERCIALLY',
	              'old-project': 'NOT_REGISTERED'}
	answers = {(ee_ + p + '/config', p): (200, {'registrationState': state}) for p, state in registered.items()}
	answers[('https://www.googleapis.com/drive/v3/about', None)] = (200, {'user': {'emailAddress': 'Ana.Perez@x.org'}})
	answers[('https://bigquery.googleapis.com/bigquery/v2/projects', None)] = \
		(200, {'projects': [{'id': 'bq-project', 'friendlyName': 'Analysis'}, {'id': 'old-project'}]})
	answers[('https://cloudresourcemanager.googleapis.com/v1/projects', 'ee-anaperez')] = \
		(200, {'projects': [{'projectId': 'all-project', 'name': 'All'}, {'projectId': 'cli-project'}]})
	session = _Google(answers)
	monkeypatch.setattr(google.auth.transport.requests, 'AuthorizedSession', lambda c: session)
	found = services.own_projects(['used-before', 'Not A Project!'])
	assert found['account'] == 'Ana.Perez@x.org' and found['register'] == services.REGISTER_URL
	assert [(p['project'], p['name'], p['registration']) for p in found['projects']] == [
		('cli-project', None, 'noncommercial'), ('ee-anaperez', None, 'noncommercial'),
		('bq-project', 'Analysis', 'commercial'), ('all-project', 'All', 'noncommercial')]
	configs = [q for url, q in session.asked if url.startswith(ee_)]
	assert sorted(configs) == sorted(['used-before', 'set-project', 'cli-project', 'ee-anaperez', 'bq-project',
	                                  'old-project', 'all-project'])  # each one once, with its own quota
	# nothing found (no network): an empty list, not an error
	monkeypatch.setattr(google.auth.transport.requests, 'AuthorizedSession', lambda c: _Google({}))
	assert services.own_projects()['projects'] == []
	assert services._project_id('ee-a') is None and services._project_id('ee-ana') == 'ee-ana'
	assert services._project_id('example.com:my-project')


def test_projects_in_the_cli_and_the_mcp_server(monkeypatch, capsys):
	from monitoreo import cli
	found = {'account': 'ana@x.org', 'register': services.REGISTER_URL,
	         'projects': [{'project': 'ee-ana-p', 'name': None, 'registration': 'noncommercial'}]}
	asked = []
	monkeypatch.setattr(services, 'own_projects', lambda known=(): asked.append(list(known)) or found)
	monkeypatch.setattr(services, 'init', lambda *a, **k: pytest.fail('connected'))
	cli.main(['--project', 'mine-123', 'projects'])
	out = capsys.readouterr().out
	assert 'ee-ana-p' in out and 'noncommercial' in out and '1 projects registered in Earth Engine of ana@x.org' in out
	assert asked == [['mine-123']] and 'monitoreo [--project P] projects' in cli.__doc__
	mcp_server = pytest.importorskip('monitoreo.mcp_server')
	assert json.loads(mcp_server.own_projects()) == found and asked[-1] == []
	assert 'own_projects' in mcp_server.NO_QUOTA_WARNING


def test_assistant_api_unforeseen_error():
	# an error that the API of the assistant does not foresee comes to the page with its cause, not as «Internal
	# Server Error» (issue #26)
	import asyncio
	from starlette.requests import Request
	from monitoreo import assistant

	class Broken:
		async def pixel(self, *a):
			raise IndexError('list index out of range')

	app = assistant.make_app(Broken(), 'tok', 8765)
	route = next(r for r in app.routes if r.path == '/api/pixel')

	async def receive():
		return {'type': 'http.request', 'body': b'{"id": 1, "lon": -3.4, "lat": 37.1}', 'more_body': False}

	request = Request({'type': 'http', 'method': 'POST', 'path': '/api/pixel', 'query_string': b'',
	                   'headers': [(b'host', b'127.0.0.1:8765'), (b'x-token', b'tok')]}, receive)
	response = asyncio.run(route.endpoint(request))
	assert response.status_code == 500
	assert json.loads(response.body) == {'error': 'IndexError: list index out of range'}
