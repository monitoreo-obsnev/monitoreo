"""Catalog of variables of MonitorEO (catalog.json): fields (what each field of a variable is), collections (dates of
the Earth Engine collections), datasets (how to cite each Earth Engine dataset, as its page of the Earth Engine catalog
suggests: references and the credit line of its terms of use), methods (references of the methods: trends, burn
severity, pixel filters, Earth Engine), references (the bibliography: citation and DOI or URL of each reference, by
its ID), variables (each with the references of its formula or algorithm), landcover (the land cover maps of the land
cover masks) and classes (the tables of classes of the categorical layers, ECOREGION and BIOME: the code, name and
colour of each class; see monitoreo.categorical). monitoreo.references gathers the references of each result."""

import json
import os
import re

CATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'catalog.json')

# Corrections of entries of catalog.json, applied when an entry is read: ref: {field: value}
FIXES = {
	32: {'scale': 0.1},  # Lai of MCD15A3H has a scale of 0.1 (raw 58 = 5.8 m2/m2 in the Amazon rain forest), not 0.01
}

# Variables added to those of catalog.json: {ref: (entry of catalog.json it copies, changes)}. Their refs start at
# 101, so that they never collide with the entries of catalog.json.
NBR_PALETTE = ['7a0403', 'c0392b', 'e67e22', 'f5cba7', 'f2efe6', 'b8e186', '7fbc41', '4d9221', '276419']
EXTRA = {
	101: (3, {'index': 'NBR', 'ft': 'N(nir,swir2)', 'f': '(SR_B5 - SR_B7) / (SR_B5 + SR_B7)'}),  # Landsat
	102: (4, {'index': 'NBR', 'ft': 'N(B8,B12)', 'f': '(B8 - B12) / (B8 + B12)'}),  # Sentinel-2
	# RBR: compares a period before and one after a fire (only burn_severity with index 'RBR'); the formula is the NBR
	# of each image: B8A and B12 in Sentinel-2 (NBR5n of Silva-Cardoza et al. 2022), NIR and SWIR2 in Landsat
	103: (4, {'index': 'RBR', 'ft': 'N(B8A,B12)', 'f': '(B8A - B12) / (B8A + B12)', 'm': 20}),  # Sentinel-2
	104: (3, {'index': 'RBR', 'ft': 'N(nir,swir2)', 'f': '(SR_B5 - SR_B7) / (SR_B5 + SR_B7)'}),  # Landsat
	# SCF: snow cover frequency, from the bands of the NDSI of Landsat (entry 5); each image is 100 (snow) or 0 (no
	# snow) with the rules of sensors.SCF, and the mean of the images of a pixel is its frequency
	105: (5, {'index': 'SCF', 'ft': 'SCF(green,nir,swir1)',
	          'f': 'NDSI = (SR_B3 - SR_B6) / (SR_B3 + SR_B6); snow: NDSI >= 0.35, SR_B3 > 0.1 and SR_B5 > 0.1 (Landsat 8 and '
	               '9; in the shadow of the relief, the NDSI >= 0.35 and the green >= 0.08 of the TOA reflectance)'}),
	# Elevation and slope of the Copernicus DEM GLO-30: fixed layers, without dates (maps and their statistics, no
	# time series, trends or comparisons: see variable.is_static); they copy no entry of catalog.json (None)
	106: (None, {'index': 'ELEVATION', 'ft': 'DEM', 'f': 'DEM', 'vname': 'Elevación', 'vname_en': 'Elevation',
	             'vname_fr': 'Elevation', 'vname_de': 'Elevation', 'unit': '[m]', 'minp': 0, 'maxp': 3500,
	             'pm': ['1a9850', '91cf60', 'd9ef8b', 'fee08b', 'fdae61', 'b2734a', '8c510a', 'bdbdbd', 'ffffff']}),
	107: (None, {'index': 'SLOPE', 'ft': 'slope(DEM)', 'f': 'ee.Terrain.slope(DEM)', 'terrain': 'slope',
	             # ee.Terrain.slope: the gradient of the 4 neighbours of each pixel (Zevenbergen & Thorne 1987)
	             'references': ['rizzoli2017', 'zevenbergen1987'],
	             'vname': 'Pendiente', 'vname_en': 'Slope', 'vname_fr': 'Slope', 'vname_de': 'Slope', 'unit': '[°]',
	             'minp': 0, 'maxp': 45,
	             'pm': ['ffffcc', 'ffeda0', 'fed976', 'feb24c', 'fd8d3c', 'fc4e2a', 'e31a1c', 'bd0026', '800026']}),
}
RBR_OFFSET = 1.001  # RBR = dNBR / (NBR before + RBR_OFFSET) (Parks et al. 2014)
RBR = {
	'vname': 'Índice Relativizado de Quema', 'vname_en': 'Relativized Burn Ratio', 'vname_fr': 'Relativized Burn Ratio',
	'vname_de': 'Relativized Burn Ratio', 'two_periods': True, 'minp': -0.5, 'maxp': 1,
	'references': ['parks2014', 'silvacardoza2022'],
	'notes': {'f': 'RBR = dNBR / (NBR before + 1.001), dNBR = NBR before - NBR after the fire, without phenological '
	               'correction and without the factor 1000 of the articles (0.478 here is 478 there), like the dNBR of '
	               'MonitorEO; NBR of B8A and B12 in Sentinel-2 (Silva-Cardoza et al. 2022, '
	               'https://doi.org/10.3390/rs14133122; Parks et al. 2014, https://doi.org/10.3390/rs6031827). It '
	               'compares two periods: burn_severity with index RBR computes it (a continuous map, no classes).'},
}
# RdNBR (Miller & Thode 2007): dNBR / sqrt(|NBR before|), with |NBR before| at least RDNBR_MIN_NBR, the qualifier of
# Howe et al. 2022 (the smallest |NBR| but 0 of the integer NBR x 1000 of the article), so that an NBR before of 0
# does not divide by 0
RDNBR_MIN_NBR = 0.001
RDNBR = {
	'vname': 'dNBR relativo', 'vname_en': 'Relative differenced Normalized Burn Ratio',
	'vname_fr': 'Relative differenced Normalized Burn Ratio', 'vname_de': 'Relative differenced Normalized Burn Ratio',
	'two_periods': True, 'minp': -0.5, 'maxp': 1.2,
	'references': ['miller2007', 'howe2022'],
	'notes': {'f': 'RdNBR = dNBR / sqrt(|NBR before|), with |NBR before| at least 0.001 (Howe et al. 2022), dNBR = NBR '
	               'before - NBR after the fire (Miller & Thode 2007, https://doi.org/10.1016/j.rse.2006.12.006), '
	               'without the offset of the dNBR of the unburned area around the fire and without the factor 1000 of '
	               'the article (0.641 here is 641 there), like the dNBR of MonitorEO. Severity classes of the article '
	               '(its Table 4, from the composite burn index of 14 fires of the Sierra Nevada of California): '
	               'unchanged < 0.069, low 0.069 to 0.316, moderate 0.316 to 0.641, high >= 0.641. NBR of B8 and B12 in '
	               'Sentinel-2 (Howe et al. 2022, https://doi.org/10.3390/rs14205249), NIR and SWIR2 in Landsat (bands 4 '
	               'and 7 of the Landsat TM of the article), bands 2 and 7 of the daily surface reflectance in MODIS '
	               '(Veraverbeke et al. 2010, https://doi.org/10.1016/j.rse.2010.05.029). It compares two periods: '
	               'burn_severity with index RdNBR computes it (a continuous map and its classes).'},
}
# The RdNBR of MODIS (see EXTRA): bands 2 (NIR, 841-876 nm) and 7 (SWIR, 2105-2155 nm) of the daily surface
# reflectance of Terra (MOD09GA) and Aqua (MYD09GA), 500 m, with the pixel filters of their band state_1km
# (sensors.PRODUCTS)
RDNBR_MODIS = {
	'sensor': 'Modis', 'm': 500, 'tr': 'daily', 'unit': '[unitless]', 'scale': 0.0001, 'offset': 0,
	'ft': 'N(sur_refl_b02,sur_refl_b07)', 'f': '(sur_refl_b02 - sur_refl_b07) / (sur_refl_b02 + sur_refl_b07)',
	'clouds_bandQA': 'state_1km', 'water_bandQA': 'state_1km', 'snow_bandQA': 'state_1km',
	'aerosols_bandQA': 'state_1km', 'large_areas': True,
	'references': ['miller2007', 'howe2022', 'veraverbeke2010'],
	'notes': dict(RDNBR['notes'], m='500 m: the classes of Miller & Thode 2007 come from Landsat (30 m); a pixel of '
	                                '500 m mixes burned and unburned land, so its RdNBR is less extreme, the hectares '
	                                'of each class are approximate and small fires are missed'),
}
NBR = {
	'type': 'Perturbaciones', 'type_en': 'Disturbances', 'type_fr': 'Disturbances', 'type_de': 'Disturbances',
	'vname': 'Índice Normalizado de Quema', 'vname_en': 'Normalized Burn Ratio',
	'vname_fr': 'Normalized Burn Ratio', 'vname_de': 'Normalized Burn Ratio', 'minp': -0.5, 'maxp': 1,
	'pm': NBR_PALETTE, 'pg': '#7a0403', 'references': ['garcia1991'],  # the NBR (Key & Benson 2006: burn severity)
	'notes': {'f': 'Burn severity: dNBR = NBR before - NBR after the fire (compare_series or download_comparison give '
	               'after - before, that is -dNBR); dNBR > 0.1 burned (Key & Benson 2006).'},
}
SCF_PALETTE = ['f7fbff', 'deebf7', 'c6dbef', '9ecae1', '6baed6', '4292c6', '2171b5', '08519c', '08306b']
SCF = {
	'vname': 'Frecuencia de nieve', 'vname_en': 'Snow cover frequency', 'vname_fr': 'Snow cover frequency',
	'vname_de': 'Snow cover frequency', 'unit': '[%]', 'minp': 0, 'maxp': 100, 'pm': SCF_PALETTE, 'pg': '#4292c6',
	'metric': 'mean',  # the only metric: the mean of the images (100 or 0) of a pixel is its frequency
	'axis': 'Snow Cover Frequency (SCF)',  # title of the y axis of the charts, before the unit
	'notes': {
		'ft': 'Snow cover frequency (SCF): % of the clear observations of each pixel with snow or ice. In the sun, snow '
		      'is NDSI >= 0.35, green > 0.1 and NIR > 0.1 (surface reflectance), without the pixels flagged as water. In '
		      'the shadow of the relief (hillShadow of the SRTM with the sun of each scene), above 1500 m, snow is NDSI '
		      '>= 0.35 and green >= 0.08 of the TOA reflectance; below 1500 m, no data. Clouds: QA_PIXEL bits 3 and 9 '
		      '(cloud shadows are kept); scenes with less than 80 % of clouds. The thresholds were set in Sierra Nevada. '
		      'Its only metric is the mean.',
		'metric': 'it is the mean of the images of each pixel (100 = snow, 0 = no snow), that is, the % of the clear '
		          'observations with snow',
		'filters': 'fixed: clouds and water are always removed and snow and aerosols never, whatever the quality',
	},
}
# The SCF of MODIS (Terra MOD10A1, Aqua MYD10A1): from the daily snow product, with the NDSI threshold of the SCF of
# Landsat (NDSI_Snow_Cover is 100 x the NDSI, 0-100; 200-255 are flags: see sensors.PRODUCTS)
SCF_MODIS_NOTES = {
	'ft': 'Snow cover frequency (SCF) of MODIS: % of the clear observations of each pixel with snow or ice, from the '
	      'daily snow product of Terra (MOD10A1) or Aqua (MYD10A1), 500 m. Each image is 100 where NDSI_Snow_Cover >= 35 '
	      '(an NDSI of 0.35, the threshold of the SCF of Landsat) and 0 where it is 0 to 34; clouds (250), inland water '
	      'and ocean (237, 239), night and the other flags (200-255) have no data. Its only metric is the mean.',
	'metric': SCF['notes']['metric'],
	'filters': SCF['notes']['filters'],
}
SCF_MODIS_F = 'NDSI_Snow_Cover >= 35 -> 100; 0-34 -> 0; 200-255 (clouds, water, night, fill values) -> no data'
# The SCF of Sentinel-2: the rules of the SCF of Landsat on its bands (sensors.SCF), its clouds from Cloud Score+
SCF_S2_NOTES = {
	'ft': 'Snow cover frequency (SCF) of Sentinel-2: % of the clear observations of each pixel with snow or ice, with the '
	      'rules of the SCF of Landsat. In the sun, snow is NDSI >= 0.35, green (B3) > 0.1 and NIR (B8) > 0.1 (L2A '
	      'surface reflectance; the NDSI with the SWIR1, B11, of 20 m), without the pixels of water of the SCL. In the '
	      'shadow of the relief (hillShadow of the SRTM with the mean sun of each scene), above 1500 m, snow is NDSI >= '
	      '0.35 and green >= 0.08 of the Level-1C TOA reflectance of the same scene; below 1500 m, no data. Clouds: '
	      'Cloud Score+ cs_cdf below 0.6; scenes with less than 80 % of clouds. The thresholds were set in Sierra '
	      'Nevada. Since 2017; an image every 5 days. Its only metric is the mean.',
	'metric': SCF['notes']['metric'],
	'filters': SCF['notes']['filters'],
}
SCF_S2_F = ('NDSI = (B3 - B11) / (B3 + B11); snow: NDSI >= 0.35, B3 > 0.1 and B8 > 0.1 (in the shadow of the relief, '
            'the NDSI >= 0.35 and the green >= 0.08 of the TOA reflectance of the Level-1C scene)')
# Snow cover days (SCD): the days with snow of each pixel, from the images of its SCF (the same rules and pixel
# filters), summed month by month (composite.days): the only metric 'days'
SCD = dict(SCF, **{
	'vname': 'Días de nieve', 'vname_en': 'Snow cover days', 'vname_fr': 'Snow cover days',
	'vname_de': 'Snow cover days', 'unit': '[days]', 'minp': 0, 'maxp': 240,
	'metric': 'days',  # the only metric: the SCF of each month times its days, summed (composite.days)
	'axis': 'Snow Cover Days (SCD)',  # title of the y axis of the charts, before the unit
	'notes': {
		'ft': 'Snow cover days (SCD): the days with snow or ice of each pixel in a window (a year, a season, a month), '
		      'estimated from the images of its snow cover frequency (SCF: each image 100 = snow or 0 = no snow, with '
		      'the rules and the pixel filters of the SCF of its sensor): the sum over the calendar months of the window '
		      'of the SCF of each month (the mean of its clear images) times the days of that month in the window. A '
		      'month without any clear image on a pixel takes the SCF of the other months of the window (their mean, '
		      'weighted by their days), so the days are the SCF of the window weighted by months times its days. With an '
		      'image every few days (Sentinel-2: 5, since 2017; Landsat: 8 to 16; fewer with clouds) it is an estimate, '
		      'better with more images (n_images); MODIS (daily, 500 m) follows the days better. Over several years or '
		      'seasons (a map of a long period) it is the mean of the days of each of them. Its only metric is days.',
		'metric': 'it is the SCF of each month times its days, summed over the months (see the formula): the snow '
		          'cover days have no other metric',
		'filters': SCF['notes']['filters'],
	},
})
EXTRA.update({
	# the SCF of MODIS Terra and Aqua, from their NDSI (entries 6 and 7)
	151: (6, {'index': 'SCF', 'ft': 'SCF(NDSI_Snow_Cover)', 'f': SCF_MODIS_F, 'notes': SCF_MODIS_NOTES,
	          'references': ['hall1995', 'riggs2017', 'hammond2018']}),
	152: (7, {'index': 'SCF', 'ft': 'SCF(NDSI_Snow_Cover)', 'f': SCF_MODIS_F, 'notes': SCF_MODIS_NOTES,
	          'references': ['hall1995', 'riggs2017', 'hammond2018']}),
	# the snow cover days of Landsat (the images of the SCF of entry 105) and of MODIS Terra and Aqua (151, 152)
	153: (5, {'index': 'SCD', 'ft': 'SCF(green,nir,swir1)', 'f': EXTRA[105][1]['f'] + '; days: the SCF of each month '
	          'x its days, summed', 'references': ['hall1995', 'macander2015']}),
	154: (6, {'index': 'SCD', 'ft': 'SCF(NDSI_Snow_Cover)', 'f': SCF_MODIS_F + '; days: the SCF of each month x its '
	          'days, summed', 'references': ['hall1995', 'riggs2017', 'hammond2018', 'gascoin2015']}),
	155: (7, {'index': 'SCD', 'ft': 'SCF(NDSI_Snow_Cover)', 'f': SCF_MODIS_F + '; days: the SCF of each month x its '
	          'days, summed', 'references': ['hall1995', 'riggs2017', 'hammond2018', 'gascoin2015']}),
	# the SCF and the snow cover days of Sentinel-2, from the bands of its NDSI (entry 8), at the 20 m of its SWIR1
	156: (8, {'index': 'SCF', 'ft': 'SCF(B3,B8,B11)', 'f': SCF_S2_F, 'm': 20, 'notes': SCF_S2_NOTES,
	          'references': ['hall1995', 'gascoin2019']}),
	157: (8, {'index': 'SCD', 'ft': 'SCF(B3,B8,B11)', 'f': SCF_S2_F + '; days: the SCF of each month x its days, '
	          'summed', 'm': 20, 'references': ['hall1995', 'gascoin2019']}),
})
# Snow melt-out day (SMOD): the day of the year when the snow of each pixel goes, from the images of its SCF (the same
# rules, shadows of the relief and pixel filters): the first clear image without snow after the last one with snow, in
# each season of each year (composite.melt): the only metric 'melt'. Earlier is blue-green, later dark blue.
SMOD_PALETTE = ['ffffd9', 'edf8b1', 'c7e9b4', '7fcdbb', '41b6c4', '1d91c0', '225ea8', '253494', '081d58']
SMOD_F = '; melt-out: the day of the year of the first clear image without snow after the last one with snow'
SMOD = dict(SCF, **{
	'vname': 'Día de deshielo', 'vname_en': 'Snow melt-out day', 'vname_fr': 'Snow melt-out day',
	'vname_de': 'Snow melt-out day', 'unit': '[day of year]', 'minp': 1, 'maxp': 243, 'pm': SMOD_PALETTE,
	'pg': '#225ea8',
	'metric': 'melt',  # the only metric: the day of the first image without snow after the last with snow (composite.melt)
	'axis': 'Snow Melt-Out Day (SMOD)',  # title of the y axis of the charts, before the unit
	'notes': {
		'ft': 'Snow melt-out day (SMOD): the day of the year (1 = 1 January) when the snow of each pixel goes, in each '
		      'season of each year (by default 1 January to 31 August: from the melt of the low mountain to before the '
		      'first snowfalls of autumn): the day of the first clear image without snow after the last image with '
		      'snow, from the images of its snow cover frequency (SCF: each image snow or no snow, with the rules, the '
		      'correction of the shadows of the relief and the pixel filters of the SCF of its sensor). A pixel '
		      'without snow in the whole season takes the day of its first clear image (the snow had gone before, or '
		      'there was none); one whose snow does not go in the season has no data. It is the day of an image, so it '
		      'can be up to the days between two clear images after the real melt-out (Sentinel-2: 5, since 2017; '
		      'Landsat: 8 to 16; more with clouds; MODIS: daily, 500 m). Over several years (a map of a long period) it '
		      'is the mean of the day of each year; a trend is in days per year (negative: earlier). A season across '
		      'the new year counts the days from the 1 January of its spring (those before are 0 or negative). Its only '
		      'metric is melt.',
		'metric': 'it is the day of the first clear image without snow after the last one with snow, in each season '
		          'of each year (see the formula): the snow melt-out day has no other metric',
		'filters': SCF['notes']['filters'],
	},
})
EXTRA.update({
	# the snow melt-out day of Landsat, MODIS Terra and Aqua and Sentinel-2, from the images of their SCF (entries 105,
	# 151, 152 and 156)
	161: (5, {'index': 'SMOD', 'ft': 'SCF(green,nir,swir1)', 'f': EXTRA[105][1]['f'] + SMOD_F,
	          'references': ['hall1995', 'barroudumont2025']}),
	162: (6, {'index': 'SMOD', 'ft': 'SCF(NDSI_Snow_Cover)', 'f': SCF_MODIS_F + SMOD_F,
	          'references': ['hall1995', 'riggs2017', 'dietz2012']}),
	163: (7, {'index': 'SMOD', 'ft': 'SCF(NDSI_Snow_Cover)', 'f': SCF_MODIS_F + SMOD_F,
	          'references': ['hall1995', 'riggs2017', 'dietz2012']}),
	164: (8, {'index': 'SMOD', 'ft': 'SCF(B3,B8,B11)', 'f': SCF_S2_F + SMOD_F, 'm': 20,
	          'references': ['hall1995', 'gascoin2019', 'barroudumont2025']}),
})
DEM = {
	'type': 'Topografía', 'type_en': 'Topography', 'type_fr': 'Topography', 'type_de': 'Topography',
	'sensor': 'Copernicus', 'col': 'COPERNICUS/DEM/GLO30_2024_1', 'band': 'DEM', 'm': 30, 'tr': 'fixed',
	'dr': 'fixed layer, without dates (TanDEM-X, 2011-2015)', 'scale': 1, 'offset': 0, 'pg': '#8c510a',
	'large_areas': True,
	'static': True,  # without dates: maps and their statistics, no time series, trends or comparisons
	'references': ['rizzoli2017'],  # the global TanDEM-X DEM, from which the Copernicus DEM comes
	'notes': {
		'ft': 'Copernicus DEM GLO-30 (release 2024_1), from the radar of TanDEM-X (2011-2015), 30 m: a surface model, '
		      'so it gives the height of the canopy and of the buildings, not that of the ground. The slope is that of '
		      'ee.Terrain.slope, in degrees (0 = flat, 90 = vertical); on pixels more than twice as big as those of '
		      'the data, the mean of the slopes of their 30 m pixels. A fixed layer, without dates: maps, GeoTIFFs and '
		      'statistics of the region, but no time series, trends or comparisons; the period, metrics and pixel '
		      'filters do not apply.',
	},
}
# MERIT Hydro v1.0.1 (Yamazaki et al. 2019): the hydrography of the MERIT DEM at 3 arc-seconds (some 90 m), an image
# (not a collection) with the hydrologically adjusted elevation (band elv, m) and the upstream drainage area (band upa,
# km²) of each pixel, among others. A fixed layer, without dates, like the DEM; its own references and notes, not
# those of the Copernicus DEM (each variable of it gives them)
MERIT_HYDRO = dict(DEM, sensor='MERIT Hydro', col='MERIT/Hydro/v1_0_1', band='elv', m=90, image_asset=True,
                   dr='fixed layer, without dates (MERIT Hydro v1.0.1, from MERIT DEM)', pg='#35978f',
                   references=[], notes={})
# CF: cloud frequency, the % of the observations of each pixel with clouds (Wilson & Jetz 2016 computed it from the
# MODIS cloud flags): each image is 100 (cloud) or 0 (clear), with the cloud flags of its sensor (sensors.cf_collection),
# and the mean of the images of a pixel is its frequency. Its pixel filters are none: clouds are what it measures.
CF_PALETTE = ['f7fbff', 'e3e8ee', 'cfd5dc', 'bbc2ca', 'a7afb8', '939ca6', '7f8994', '6b7682', '576370']
CF = {
	'type': 'Clima', 'type_en': 'Climate', 'type_fr': 'Climate', 'type_de': 'Climate',
	'vname': 'Frecuencia de nubes', 'vname_en': 'Cloud frequency', 'vname_fr': 'Cloud frequency',
	'vname_de': 'Cloud frequency', 'unit': '[%]', 'minp': 0, 'maxp': 100, 'pm': CF_PALETTE, 'pg': '#7f8994',
	'scale': 1, 'offset': 0, 'large_areas': True,
	'metric': 'mean',  # the only metric: the mean of the images (100 or 0) of a pixel is its frequency
	'axis': 'Cloud Frequency (CF)',  # title of the y axis of the charts, before the unit
	'references': ['wilson2016'],
	'notes': {
		'ft': 'Cloud frequency (CF): % of the observations of each pixel with clouds. Each image is 100 where its cloud '
		      'flags say cloud and 0 where they say clear: MODIS, state_1km bits 0-1 cloudy or mixed; Sentinel-2, Cloud '
		      'Score+ cs_cdf below 0.6 (the threshold of the cloud filter of MonitorEO); Landsat, QA_PIXEL bit 3 '
		      '(cloud) or bit 9 (medium or high cloud confidence). Cloud shadows are not clouds. Its only metric is the '
		      'mean, and it has no pixel filters: clouds are what it measures. MODIS (daily, 1 km) gives the frequency '
		      'of the climate; Sentinel-2 and Landsat, with an image every 5 to 16 days, only at the time they pass.',
		'metric': 'it is the mean of the images of each pixel (100 = cloud, 0 = clear), that is, the % of the '
		          'observations with clouds',
		'filters': 'none: clouds are what it measures, so no pixel filter applies',
	},
}
# Climate: monthly series of ERA5-Land (reanalysis, 11 km) and TerraClimate (4.6 km), daily precipitation of CHIRPS v3
# (5.5 km) and the bioclimatic variables of WorldClim 1.4 (1960-1990, 1 km, fixed layers). They have no pixel filters
# (no QA bands); the totals of a period (e.g. the annual precipitation) are the metric 'sum' of their images.
CLIMATE_TYPE = {'type': 'Clima', 'type_en': 'Climate', 'type_fr': 'Climate', 'type_de': 'Climate', 'large_areas': True}
PRECIP_PALETTE = ['ffffff', 'deebf7', 'c6dbef', '9ecae1', '6baed6', '4292c6', '2171b5', '08519c', '08306b']
TEMP_PALETTE = ['313695', '4575b4', '74add1', 'abd9e9', 'ffffbf', 'fee090', 'fdae61', 'f46d43', 'd73027', 'a50026']
WATER_PALETTE = ['ffffe5', 'fff7bc', 'fee391', 'fec44f', 'fe9929', 'ec7014', 'cc4c02', '993404', '662506']
SOIL_PALETTE = ['8c510a', 'bf812d', 'dfc27d', 'f6e8c3', 'c7eae5', '80cdc1', '35978f', '01665e', '003c30']
ERA5L = dict(CLIMATE_TYPE, sensor='ERA5-Land', col='ECMWF/ERA5_LAND/MONTHLY_AGGR', m=11132, tr='monthly',
             dr='1950/02/01-now (a few months behind)', scale=1, offset=0, pg='#2171b5',
             references=['munozsabater2021'],
             notes={'ft': 'ERA5-Land (ECMWF, Copernicus Climate Change Service): a reanalysis of the land at 0.1° (some '
                          '11 km), monthly, from 1950 to a few months ago: a model fed with observations, for the '
                          'climate of a region, not of a plot. Precipitation in mm of each month (the sum of a year is '
                          'its total); temperatures of the air at 2 m in °C (the mean, minimum and maximum of each '
                          'month). No pixel filters.'})
TERRACLIMATE = dict(CLIMATE_TYPE, sensor='TerraClimate', col='IDAHO_EPSCOR/TERRACLIMATE', m=4638, tr='monthly',
                    dr='1958/01/01-2024/12/31', scale=1, offset=0, pg='#2171b5', references=['abatzoglou2018'],
                    notes={'ft': 'TerraClimate: monthly climate and water balance at 1/24° (some 4.6 km), 1958-2024, '
                                 'from WorldClim, CRU and JRA55. Precipitation, reference (PET) and actual (AET) '
                                 'evapotranspiration and climatic water deficit (CWD = PET - AET) in mm of each month, '
                                 'soil moisture in mm at the end of the month, vapour pressure deficit in kPa, minimum '
                                 'and maximum temperatures in °C. No pixel filters.'})
CHIRPS = dict(CLIMATE_TYPE, sensor='CHIRPS', col='UCSB-CHC/CHIRPS/V3/DAILY_SAT', m=5566, tr='daily',
              dr='1981/01/01-now (60°S-60°N)', scale=1, offset=0, pg='#2171b5', references=['funk2015'],
              notes={'ft': 'CHIRPS v3 (Climate Hazards Center): daily precipitation in mm at 0.05° (some 5.5 km) from '
                           'satellite infrared and rain gauges, 1981 to now, only between 60°S and 60°N. The sum of a '
                           'month or a year is its total. No pixel filters.'})
WORLDCLIM = dict(CLIMATE_TYPE, sensor='WorldClim', col='WORLDCLIM/V1/BIO', m=928, tr='fixed',
                 dr='fixed layer, without dates (climate of 1960-1990)', offset=0, pg='#d73027',
                 static=True, image_asset=True, references=['hijmans2005'],  # an image, not a collection
                 notes={'ft': 'WorldClim 1.4 (Hijmans et al. 2005): the 19 bioclimatic variables of the climate of '
                              '1960-1990, interpolated from weather stations at 30 arc-seconds (some 1 km). Fixed '
                              'layers, without dates: maps, GeoTIFFs and statistics of the region, but no time series, '
                              'trends or comparisons. Licence CC BY-SA 4.0.'})


def _climate(index, ft, names, unit, lo, hi, palette, **more):
	"""The fields of a climate variable (see EXTRA): its index, formula, names (Spanish, English) and colour ramp."""
	es, en = names
	return dict({'index': index, 'ft': ft, 'f': ft, 'vname': es, 'vname_en': en, 'vname_fr': en, 'vname_de': en,
	             'unit': unit, 'minp': lo, 'maxp': hi, 'pm': palette}, **more)


PRECIP = ('Precipitación', 'Precipitation')
EXTRA.update({
	# cloud frequency of MODIS Terra and Aqua (daily, 1 km), Sentinel-2 (10 m) and Landsat (30 m)
	108: (None, dict(index='CF', ft='CF(state_1km)', template='CF', sensor='Modis', col='MODIS/061/MOD09GA', m=1000,
	                 tr='daily', dr='2000/02/24-now', f='state_1km bits 0-1: 1 (cloudy) or 2 (mixed) -> 100; 0 (clear) '
	                 'or 3 (assumed clear) -> 0')),
	109: (None, dict(index='CF', ft='CF(state_1km)', template='CF', sensor='Modis', col='MODIS/061/MYD09GA', m=1000,
	                 tr='daily', dr='2002/07/04-now', f='state_1km bits 0-1: 1 (cloudy) or 2 (mixed) -> 100; 0 (clear) '
	                 'or 3 (assumed clear) -> 0')),
	110: (None, dict(index='CF', ft='CF(cs_cdf)', template='CF', sensor='Sentinel-2', col='COPERNICUS/S2_SR_HARMONIZED',
	                 m=10, tr='5-days', dr='2017/03/28-now', f='Cloud Score+ cs_cdf < 0.6 -> 100; else 0',
	                 references=['wilson2016', 'pasquarella2023'])),
	111: (None, dict(index='CF', ft='CF(QA_PIXEL)', template='CF', sensor='Landsat', col='LANDSAT', m=30,
	                 tr='16-days', dr='1984/03/16-now', f='QA_PIXEL bit 3 (cloud) or bit 9 (medium or high cloud '
	                 'confidence) -> 100; else 0', references=['wilson2016', 'foga2017'])),
	# ERA5-Land, monthly (temperatures in K, precipitation in m of each month)
	112: (None, _climate('PRECIP', 'total_precipitation_sum', PRECIP, '[mm/month]', 0, 200, PRECIP_PALETTE,
	                     template='ERA5L', scale=1000)),
	113: (None, _climate('TMEAN', 'temperature_2m', ('Temperatura media del aire', 'Mean air temperature'), '[°C]',
	                     -10, 35, TEMP_PALETTE, template='ERA5L', offset=-273.15)),
	114: (None, _climate('TMIN', 'temperature_2m_min', ('Temperatura mínima del aire', 'Minimum air temperature'),
	                     '[°C]', -20, 30, TEMP_PALETTE, template='ERA5L', offset=-273.15)),
	115: (None, _climate('TMAX', 'temperature_2m_max', ('Temperatura máxima del aire', 'Maximum air temperature'),
	                     '[°C]', -5, 45, TEMP_PALETTE, template='ERA5L', offset=-273.15)),
	# TerraClimate, monthly (temperatures and water balance x 0.1, vapour pressure deficit x 0.01)
	116: (None, _climate('PRECIP', 'pr', PRECIP, '[mm/month]', 0, 200, PRECIP_PALETTE, template='TERRACLIMATE')),
	117: (None, _climate('TMIN', 'tmmn', ('Temperatura mínima del aire', 'Minimum air temperature'), '[°C]', -20, 30,
	                     TEMP_PALETTE, template='TERRACLIMATE', scale=0.1)),
	118: (None, _climate('TMAX', 'tmmx', ('Temperatura máxima del aire', 'Maximum air temperature'), '[°C]', -5, 45,
	                     TEMP_PALETTE, template='TERRACLIMATE', scale=0.1)),
	119: (None, _climate('PET', 'pet', ('Evapotranspiración de referencia', 'Reference evapotranspiration'),
	                     '[mm/month]', 0, 250, WATER_PALETTE, template='TERRACLIMATE', scale=0.1)),
	120: (None, _climate('AET', 'aet', ('Evapotranspiración real', 'Actual evapotranspiration'), '[mm/month]', 0, 150,
	                     WATER_PALETTE, template='TERRACLIMATE', scale=0.1)),
	121: (None, _climate('CWD', 'def', ('Déficit hídrico climático', 'Climatic water deficit'), '[mm/month]', 0, 200,
	                     WATER_PALETTE, template='TERRACLIMATE', scale=0.1)),
	122: (None, _climate('SOILM', 'soil', ('Humedad del suelo', 'Soil moisture'), '[mm]', 0, 300, SOIL_PALETTE,
	                     template='TERRACLIMATE', scale=0.1)),
	123: (None, _climate('VPD', 'vpd', ('Déficit de presión de vapor', 'Vapour pressure deficit'), '[kPa]', 0, 3,
	                     WATER_PALETTE, template='TERRACLIMATE', scale=0.01)),
	# CHIRPS v3, daily
	124: (None, _climate('PRECIP', 'precipitation', PRECIP, '[mm/day]', 0, 20, PRECIP_PALETTE, template='CHIRPS')),
})
# WorldClim 1.4: the 19 bioclimatic variables (band, Spanish and English names, unit, colour ramp, scale)
BIOCLIM = [
	('Temperatura media anual', 'Annual mean temperature', '[°C]', -10, 30, 0.1),
	('Oscilación diurna media', 'Mean diurnal range', '[°C]', 0, 20, 0.1),
	('Isotermalidad', 'Isothermality', '[%]', 0, 100, 1),
	('Estacionalidad de la temperatura (desviación típica)', 'Temperature seasonality (standard deviation)', '[°C]', 0,
	 15, 0.01),
	('Temperatura máxima del mes más cálido', 'Max temperature of the warmest month', '[°C]', 0, 45, 0.1),
	('Temperatura mínima del mes más frío', 'Min temperature of the coldest month', '[°C]', -30, 20, 0.1),
	('Oscilación anual de la temperatura', 'Temperature annual range', '[°C]', 0, 50, 0.1),
	('Temperatura media del trimestre más húmedo', 'Mean temperature of the wettest quarter', '[°C]', -20, 35, 0.1),
	('Temperatura media del trimestre más seco', 'Mean temperature of the driest quarter', '[°C]', -20, 35, 0.1),
	('Temperatura media del trimestre más cálido', 'Mean temperature of the warmest quarter', '[°C]', -20, 35, 0.1),
	('Temperatura media del trimestre más frío', 'Mean temperature of the coldest quarter', '[°C]', -20, 35, 0.1),
	('Precipitación anual', 'Annual precipitation', '[mm]', 0, 3000, 1),
	('Precipitación del mes más húmedo', 'Precipitation of the wettest month', '[mm]', 0, 500, 1),
	('Precipitación del mes más seco', 'Precipitation of the driest month', '[mm]', 0, 200, 1),
	('Estacionalidad de la precipitación (coeficiente de variación)', 'Precipitation seasonality (coefficient of '
	 'variation)', '[%]', 0, 150, 1),
	('Precipitación del trimestre más húmedo', 'Precipitation of the wettest quarter', '[mm]', 0, 1500, 1),
	('Precipitación del trimestre más seco', 'Precipitation of the driest quarter', '[mm]', 0, 500, 1),
	('Precipitación del trimestre más cálido', 'Precipitation of the warmest quarter', '[mm]', 0, 1500, 1),
	('Precipitación del trimestre más frío', 'Precipitation of the coldest quarter', '[mm]', 0, 1500, 1),
]
for i, (es, en, unit, lo, hi, scale) in enumerate(BIOCLIM, 1):
	EXTRA[124 + i] = (None, _climate(f'BIO{i:02d}', f'bio{i:02d}', (es, en), unit, lo, hi,
	                                 PRECIP_PALETTE if unit == '[mm]' else TEMP_PALETTE, template='WORLDCLIM',
	                                 band=f'bio{i:02d}', scale=scale))

# RdNBR: compares a period before and one after a fire (only burn_severity with index 'RdNBR'), with the severity
# classes of Miller & Thode 2007 (fire.RDNBR_SEVERITY); the formula is the NBR of each image: B8 and B12 in
# Sentinel-2 (Howe et al. 2022), NIR and SWIR2 in Landsat, bands 2 and 7 of MODIS Terra and Aqua (Veraverbeke et al.
# 2010)
EXTRA.update({
	144: (4, {'index': 'RdNBR', 'ft': 'N(B8,B12)', 'f': '(B8 - B12) / (B8 + B12)'}),  # Sentinel-2
	145: (3, {'index': 'RdNBR', 'ft': 'N(nir,swir2)', 'f': '(SR_B5 - SR_B7) / (SR_B5 + SR_B7)'}),  # Landsat
	146: (None, dict(RDNBR_MODIS, index='RdNBR', col='MODIS/061/MOD09GA', dr='2000/02/24-now')),  # MODIS Terra
	147: (None, dict(RDNBR_MODIS, index='RdNBR', col='MODIS/061/MYD09GA', dr='2002/07/04-now')),  # MODIS Aqua
})

# TWI: the topographic wetness index (Beven & Kirkby 1979) of MERIT Hydro, ln(a / tan β) from its bands elv and upa
# (formula TWI(elv,upa), computed as sensors.TWI says, on the grid of the data: see variable._twi); a fixed layer,
# without dates, of the theme Terrain
EXTRA[148] = (None, {
	'index': 'TWI', 'template': 'MERIT_HYDRO', 'ft': 'TWI(elv,upa)',
	'f': 'ln(a / max(tan(slope(elv)), 0.001)), a = max(upa × 10^6, pixel area) / sqrt(pixel area)',
	'references': ['beven1979', 'marthews2015', 'zevenbergen1987'],
	'vname': 'Índice topográfico de humedad', 'vname_en': 'Topographic wetness index',
	'vname_fr': 'Topographic wetness index', 'vname_de': 'Topographic wetness index', 'unit': '[unitless]',
	'minp': 4, 'maxp': 20, 'pm': SOIL_PALETTE,  # brown (dry) to teal (wet)
	'notes': {
		'ft': 'Topographic wetness index (TWI) of MERIT Hydro v1.0.1, 90 m (3 arc-seconds): how wet the soil tends to '
		      'be because of the relief alone, high in the valley bottoms and flats where the water of the slopes '
		      'above converges, low on the ridges and steep slopes. TWI = ln(a / tan β), with a the upstream drainage '
		      'area of each pixel (band upa, from the single flow directions, D8, of MERIT Hydro) per metre of '
		      'contour: at least the area of the pixel, divided by the square root of its area (Marthews et al. '
		      '2015); and β the slope of the hydrologically adjusted elevation (band elv, ee.Terrain.slope), with '
		      'tan β at least 0.001 on the flats (Marthews et al. 2015). D8 gives lower values on the hillslopes than '
		      'the indices of multiple flow directions. Computed on the grid of MERIT Hydro; on pixels more than twice '
		      'as big, the mean of the TWI of their 90 m pixels (the mean of the logarithms). Values from about 3.5 to '
		      '30, most land between 5 and 15; rivers and lakes are kept, and give the highest values. MERIT Hydro is '
		      'licensed under CC BY-NC 4.0 or ODbL 1.0. A fixed layer, without dates: maps, GeoTIFFs and statistics of '
		      'the region, but no time series, trends or comparisons; the period, metrics and pixel filters do not '
		      'apply.',
	},
})
# The ecoregions and biomes of RESOLVE Ecoregions 2017 (Dinerstein et al. 2017): categorical fixed layers, whose values
# are class codes (the ECO_ID of each ecoregion, the BIOME_NUM of each biome), with their tables of classes in classes of
# catalog.json (see monitoreo.categorical). The polygons are rasterized once, the ECO_ID of each pixel, and the biome
# comes from it with the table, so that both layers have the same boundaries.
CLASS_UNIT = '[class]'  # the unit of a categorical layer: its values are class codes, without a unit
RESOLVE = {
	'type': 'Ecosistemas', 'type_en': 'Ecosystems', 'type_fr': 'Ecosystems', 'type_de': 'Ecosystems',
	'sensor': 'RESOLVE', 'col': 'RESOLVE/ECOREGIONS/2017', 'm': 1000, 'tr': 'fixed',
	'dr': 'fixed layer, without dates (RESOLVE Ecoregions 2017)', 'unit': CLASS_UNIT, 'scale': 1, 'offset': 0,
	'pg': '#38a700', 'large_areas': True,
	'static': True,  # without dates: maps and their statistics, no time series, trends or comparisons
	'references': ['dinerstein2017'],
	'notes': {
		'ft': 'RESOLVE Ecoregions 2017 (Dinerstein et al. 2017): 846 terrestrial ecoregions and Rock and Ice in 14 '
		      'biomes, polygons rasterized by MonitorEO: the ECO_ID of the polygon of each pixel (reduceToImage with the '
		      'first feature; the pixels outside every polygon, e.g. the sea and the big lakes, have no data), and the '
		      'biome of each pixel from its ECO_ID with the table of classes of MonitorEO, so that both layers have the '
		      'same boundaries. Nominal pixel of 1 km (that of the downloads and statistics by default; maps are '
		      'rasterized at their own pixel, which does not make the boundaries more accurate); on pixels more than '
		      'twice as big, the majority class (mode) of its pixels of 1 km. Its values are class codes, not '
		      'quantities: maps with a legend of the classes, the area of each class (area_by_class), the majority '
		      'class over a region (region_stats), zones by class and conditions of where that keep or leave out some '
		      'classes (list_classes gives their codes); they are never interpolated nor averaged. Rock and Ice (ECO_ID '
		      '0) is the biome 99, a code of MonitorEO, as in the WWF terrestrial ecoregions of 2001 (in the data it has '
		      'BIOME_NUM 11, that of Tundra, with BIOME_NAME N/A). The biome of each ecoregion is that of the data: e.g. '
		      'ECO_ID 316 Godavari-Krishna mangroves is in biome 13, Deserts & Xeric Shrublands. A fixed layer, '
		      'without dates: maps, GeoTIFFs and statistics of the region, but no time series, trends or comparisons; '
		      'the period, metrics and pixel filters do not apply. Licence CC BY 4.0.',
	},
}
EXTRA.update({
	149: (None, {'index': 'ECOREGION', 'template': 'RESOLVE', 'ft': 'ECO_ID', 'band': 'ECO_ID', 'classes': 'ecoregions',
	             'f': 'ECO_ID of the polygon of each pixel (reduceToImage, first)', 'vname': 'Ecorregión',
	             'vname_en': 'Ecoregion', 'vname_fr': 'Ecoregion', 'vname_de': 'Ecoregion'}),
	150: (None, {'index': 'BIOME', 'template': 'RESOLVE', 'ft': 'BIOME_NUM', 'band': 'BIOME_NUM', 'classes': 'biomes',
	             'f': 'BIOME_NUM of the ECO_ID of each pixel (remap with the table of classes; Rock and Ice: 99)',
	             'vname': 'Bioma', 'vname_en': 'Biome', 'vname_fr': 'Biome', 'vname_de': 'Biome'}),
})

TEMPLATES = {'NBR': NBR, 'RBR': dict(NBR, **RBR), 'RdNBR': dict(NBR, **RDNBR), 'SCF': SCF, 'SCD': SCD, 'SMOD': SMOD, 'ELEVATION': DEM, 'SLOPE': DEM, 'CF': CF,
             'ERA5L': ERA5L, 'TERRACLIMATE': TERRACLIMATE, 'CHIRPS': CHIRPS, 'WORLDCLIM': WORLDCLIM,
             'MERIT_HYDRO': MERIT_HYDRO, 'RESOLVE': RESOLVE}  # fields of EXTRA

# The units of the catalog (as shown) in UDUNITS (the units of the CF conventions, read by cf-units, xarray, R units),
# for the files: '1' is dimensionless. ET is a total of 8 days (8 kg m-2 per 8 days = 1 kg m-2 per day).
UDUNITS = {
	'[unitless]': '1',
	'[°C]': 'degC',
	'[kg/m²/8 days]': 'kg m-2 (8 day)-1',
	'[J/m²/day]': 'J m-2 day-1',
	'[mg m⁻³]': 'mg m-3',
	'[%]': '%',  # the snow cover frequency (UDUNITS percent)
	'[days]': 'day',  # the snow cover days
	'[day of year]': 'day',  # the snow melt-out day: days since the 31 December before (1 = 1 January)
	'[m]': 'm',  # the elevation
	'[°]': 'degree',  # the slope, an angle (UDUNITS arc_degree)
	'[mm]': 'mm',  # the soil moisture, the precipitation of the bioclimatic variables
	'[mm/month]': 'mm month-1',  # monthly precipitation and water balance
	'[mm/day]': 'mm day-1',  # daily precipitation
	'[kPa]': 'kPa',  # the vapour pressure deficit
	# the class codes of a categorical layer (ECOREGION, BIOME): no unit, not even 1 (dimensionless), as the flag values
	# of the CF conventions, whose meaning is in their flag_values and flag_meanings, not in a units attribute; the
	# files say what each code is (the classes in the README and the metadata of the GeoTIFF), and give no unit
	CLASS_UNIT: '',
}
NO_UDUNITS = (CLASS_UNIT,)  # the units of the catalog without a UDUNITS name, on purpose (see UDUNITS)

RGB_UNIT = '[unitless]'  # the true colour of the images: surface reflectance (see sensors.RGB)

# A unit written in UDUNITS (that of the data of Earth Engine outside the catalog, given by the user: 'mm', 'degC',
# 'kg m-2', 'mm day-1', 'W m-2', '1'): letters, digits, spaces and . ^ ( ) * / % + -
UDUNITS_TEXT = re.compile(r'[A-Za-z0-9 ._^()*/%+-]+')

_catalog = None


def custom_unit(unit):
	"""The unit of the data of Earth Engine outside the catalog, whose unit UNIT is in UDUNITS ('mm', '1'), as the
	results give it: in UDUNITS, without the brackets of the units of the catalog ('mm'; '[unitless]' if
	dimensionless, as in the catalog), so that udunits keeps it."""
	unit = str(unit or '').strip()
	return '[unitless]' if unit == '1' else unit


# A rate per month or per day, whose sum is a total: in the catalog ('[mm/month]', '[mm/day]') and in UDUNITS (the
# data of Earth Engine outside the catalog: 'mm month-1', 'mm day-1'); in UDUNITS also per period of its images, the
# total of N days of each one ('mm (5 day)-1' of CHIRPS PENTAD, 'kg m-2 (8 day)-1' of an 8-day product, written
# '/N days' too) and 'd-1'. The units of the catalog keep their own (its ET of 8 days and LE are as they are).
RATE = re.compile(r'^(\[)(.+?)(?:/(?:month|day)| (?:month|day)-1)(\])$')
RATE_UDUNITS = re.compile(r'^()(.+?)(?:/(?:month|day|d|\d+ ?days?|\(\d+ ?days?\))| '
                          r'(?:month|day|d|\(\d+ ?days?\))-1)()$')


CV_UNIT = '[%]'  # the coefficient of variation (composite.CV): 100 × the standard deviation / the mean
# the statistics over each feature of a region of services.region_stats by default (any metric of composite.METRICS)
REGION_STATS = ('mean', 'std', 'cv', 'min', 'p5', 'p50', 'p95', 'max')
# and with zones (region_stats with zones), also the percentiles 25 and 75: the band of the chart of the median of each
# zone, as in the QGIS plugin and the Earth Engine app
REGION_STATS_ZONES = ('mean', 'std', 'cv', 'min', 'p5', 'p25', 'p50', 'p75', 'p95', 'max')


def is_cv(*metrics):
	"""Whether any of METRICS (a metric of the images, between the years or over a region) is the coefficient of
	variation, whose values are in %."""
	return any(str(m or '').strip().lower() == 'cv' for m in metrics)


def unit_of(unit, metric=None, interannual=None, stat=None):
	"""The unit of a variable whose unit is UNIT (of the catalog, or in UDUNITS of the data of Earth Engine outside it)
	when its images are aggregated with METRIC (and between the years with INTERANNUAL, if they are), and then over a
	region with STAT: the coefficient of variation ('cv') of any of them is in % ('[%]'; '%' in UDUNITS); the sum of a
	rate per month or per day ('[mm/month]', e.g. the annual precipitation; 'mm month-1' in UDUNITS) or per the days of
	each image ('mm (5 day)-1') is a total ('[mm]', 'mm'); the other metrics keep it."""
	text = str(unit or '')
	if is_cv(metric, interannual, stat):
		return CV_UNIT if text.startswith('[') else '%'
	m = (RATE if text.startswith('[') else RATE_UDUNITS).match(text)
	return f'{m.group(1)}{m.group(2)}{m.group(3)}' if m and str(metric or '').lower() == 'sum' else unit


def udunits(unit, per_year=False):
	"""The unit UNIT of the catalog (e.g. '[°C]') in UDUNITS ('degC'; PER_YEAR: 'degC year-1'), or '' if unknown.
	The units of the data of Earth Engine outside the catalog are already in UDUNITS, without brackets (see
	custom_unit): 'mm day-1' is 'mm day-1'."""
	text = str(unit or '').replace('º', '°').strip()
	u = UDUNITS.get(text, '')
	if not u and not text.startswith('[') and UDUNITS_TEXT.fullmatch(text):
		u = text
	if per_year and u:
		return 'year-1' if u == '1' else f'{u} year-1'
	return u


def load():
	"""The whole catalog: fields, collections (date ranges) and variables."""
	global _catalog
	if _catalog is None:
		with open(CATALOG, encoding='utf-8') as f:
			_catalog = json.load(f)
	return _catalog


# Themes: the menus of the tools with one (the QGIS plugin, the Earth Engine app), where the user chooses a theme and
# then sees its variables and its analyses. Every variable of the catalog is in one theme (tests check it), and so is
# every analysis of one kind of variable ('analyses': burn_severity for the fires); the general analyses (maps, time
# series, trends, comparisons, exports) are in every theme with variables with dates. A new kind of variable or
# analysis (e.g. species distribution models) gets its theme here, with its variables and analyses, in every menu.
THEMES = [
	{'key': 'vegetation', 'en': 'Vegetation', 'es': 'Vegetación', 'indices': ['NDVI', 'EVI', 'LAI', 'CLre', 'CLreB7', 'WAVI']},
	{'key': 'water', 'en': 'Water', 'es': 'Agua', 'indices': ['NDWI', 'LSWI', 'Chl-a', 'NDCI']},
	{'key': 'snow', 'en': 'Snow', 'es': 'Nieve', 'indices': ['NDSI', 'SCF', 'SCD', 'SMOD']},
	{'key': 'fire', 'en': 'Fire', 'es': 'Incendios', 'indices': ['NBR', 'RBR', 'RdNBR'], 'analyses': ['burn_severity']},
	{'key': 'energy', 'en': 'Energy and temperature', 'es': 'Energía y temperatura',
	 'indices': ['LST', 'ALBEDO', 'ET', 'LE']},
	{'key': 'atmosphere', 'en': 'Atmosphere', 'es': 'Atmósfera', 'indices': ['ARSL', 'CF']},
	{'key': 'climate', 'en': 'Climate', 'es': 'Clima',
	 'indices': ['PRECIP', 'TMEAN', 'TMIN', 'TMAX', 'PET', 'AET', 'CWD', 'SOILM', 'VPD']
	            + [f'BIO{i:02d}' for i in range(1, 20)]},
	{'key': 'terrain', 'en': 'Terrain', 'es': 'Relieve', 'indices': ['ELEVATION', 'SLOPE', 'TWI']},
	{'key': 'ecosystems', 'en': 'Ecosystems', 'es': 'Ecosistemas', 'indices': ['ECOREGION', 'BIOME']},
]

# The themes of the menus for the data of Earth Engine outside the catalog (no variables of it): any image or collection
# of images by its ID, and the datasets of the GEE Community Catalog by its own themes (monitoreo.community). The
# general analyses (maps, series, trends, comparisons, exports) are in both; series, trends and comparisons only for
# collections with dates (monitoreo.assets).
OTHER_THEMES = [
	{'key': 'earth_engine', 'en': 'Earth Engine data (by its ID)', 'es': 'Datos de Earth Engine (por su ID)',
	 'help': 'any image or collection of images of Earth Engine by its ID: describe it (its bands, units and dates), '
	         'then compute it with its ID as a collection or an image, and its band'},
	{'key': 'community', 'en': 'GEE Community Catalog', 'es': 'Catálogo de la comunidad de GEE',
	 'help': 'the datasets of the GEE Community Catalog by its own themes: list its themes and their datasets, describe '
	         'one, then compute it with its ID as a collection or an image, and its band'},
]  # 'help' in the words of every tool (no function or argument of one of them): the command line and R show it too


def classes_table(key):
	"""The table of classes KEY of catalog.json ('ecoregions' or 'biomes'; see monitoreo.categorical): {'name',
	'dataset', 'property', 'fields', 'group', 'notes', 'classes': {code: [values of its fields]}}."""
	return load()['classes'][key]


def biomes(lang='en'):
	"""The biomes of RESOLVE Ecoregions 2017 (the classes of BIOME): [{'code', 'name' (in Spanish with LANG 'es'),
	'colour'}], from the lowest code; Rock and Ice is 99, a code of MonitorEO (in the data, the ECO_ID 0 has BIOME_NUM
	11, that of Tundra, with BIOME_NAME N/A)."""
	t = classes_table('biomes')
	out = []
	for code, values in sorted(t['classes'].items(), key=lambda x: int(x[0])):
		row = dict(zip(t['fields'], values))
		out.append({'code': int(code), 'name': (row.get('name_es') if lang == 'es' else None) or row['name'],
		            'colour': row['colour']})
	return out


def ecoregions_of_biome(code):
	"""The ECO_IDs of the ecoregions of the biome CODE (as the table of classes gives them, those of the data; 99, Rock
	and Ice, is the ECO_ID 0), from the lowest: the polygons of a biome are those of these ECO_IDs (not those of its
	BIOME_NUM, which for Rock and Ice is 11)."""
	t = classes_table('ecoregions')
	i = t['fields'].index('group')
	return sorted(int(eco) for eco, values in t['classes'].items() if int(values[i]) == int(code))


def theme_of(index):
	"""The theme (see THEMES) of the variable INDEX, or None if it has none."""
	return next((t for t in THEMES if index in t['indices']), None)


def variables():
	"""Entries of the catalog, with FIXES applied, and those of EXTRA, each with the key of its theme (see THEMES)."""
	entries = [dict(e, **FIXES.get(e['ref'], {})) for e in load()['variables']]
	by_ref = {e['ref']: e for e in entries}
	extra = []
	for ref, (base, changes) in EXTRA.items():
		if base is not None and base not in by_ref:
			continue
		changes = dict(changes)
		template = TEMPLATES[changes.pop('template', changes['index'])]
		extra.append(dict(by_ref[base] if base is not None else {}, **dict(template, **changes), ref=ref))
	return [dict(e, theme=(theme_of(e['index']) or {}).get('key')) for e in entries + extra]


def name_key(name):
	"""NAME (of a variable or a sensor) as the catalog compares it: in lower case and without spaces ('MERIT Hydro',
	'merit hydro' and 'MERITHydro' are the same sensor)."""
	return str(name).lower().replace(' ', '')


def find(index, sensor=None, collection=None, ref=None):
	"""Entry of the catalog of a variable: by REF, or by INDEX (e.g. 'NDVI') and SENSOR ('Sentinel-2', 'Landsat',
	'Modis') and, when several collections have them (e.g. MOD13Q1 and MYD13Q1), COLLECTION. Without COLLECTION
	the first entry of the catalog is used. Names are case insensitive, and their spaces do not matter (name_key)."""
	entries = variables()
	if ref is not None:
		for e in entries:
			if e['ref'] == int(ref):
				return e
		raise KeyError(f'no entry with ref {ref} in the catalog of MonitorEO')
	low = name_key
	matches = [e for e in entries if low(e['index']) == low(index)
	           and (sensor is None or low(e['sensor']) == low(sensor))
	           and (collection is None or e['col'] == collection)]
	if not matches:
		options = sorted({f"{e['index']} ({e['sensor']})" for e in entries
		                  if low(e['index']) == low(index) or sensor is None})
		raise KeyError(f"{index} with sensor {sensor}{f' and collection {collection}' if collection else ''} "
		               f"is not in the catalog of MonitorEO. Options: {', '.join(options) or 'see the list of variables (list_variables)'}")
	return matches[0]


def alternatives(entry):
	"""Other entries with the same variable and sensor (other collections)."""
	return [e for e in variables() if e['index'] == entry['index'] and e['sensor'] == entry['sensor']
	        and e['ref'] != entry['ref']]


def table():
	"""Rows (ref, variable, sensor, collection, resolution, dates, unit, formula) to list the catalog."""
	return [(e['ref'], e['index'], e['sensor'], e['col'], e['m'], e['dr'], e['unit'], e['ft'])
	        for e in variables()]
