"""Catalog of variables of MonitorEO (catalog.json)."""

import json
import os

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
	             'vname': 'Pendiente', 'vname_en': 'Slope', 'vname_fr': 'Slope', 'vname_de': 'Slope', 'unit': '[º]',
	             'minp': 0, 'maxp': 45,
	             'pm': ['ffffcc', 'ffeda0', 'fed976', 'feb24c', 'fd8d3c', 'fc4e2a', 'e31a1c', 'bd0026', '800026']}),
}
RBR_OFFSET = 1.001  # RBR = dNBR / (NBR before + RBR_OFFSET) (Parks et al. 2014)
RBR = {
	'vname': 'Índice Relativizado de Quema', 'vname_en': 'Relativized Burn Ratio', 'vname_fr': 'Relativized Burn Ratio',
	'vname_de': 'Relativized Burn Ratio', 'two_periods': True, 'minp': -0.5, 'maxp': 1,
	'notes': {'f': 'RBR = dNBR / (NBR before + 1.001), dNBR = NBR before - NBR after the fire, without phenological '
	               'correction and without the factor 1000 of the articles (0.478 here is 478 there), like the dNBR of '
	               'MonitorEO; NBR of B8A and B12 in Sentinel-2 (Silva-Cardoza et al. 2022, '
	               'https://doi.org/10.3390/rs14133122; Parks et al. 2014, https://doi.org/10.3390/rs6031827). It '
	               'compares two periods: burn_severity with index RBR computes it (a continuous map, no classes).'},
}
NBR = {
	'type': 'Perturbaciones', 'type_en': 'Disturbances', 'type_fr': 'Disturbances', 'type_de': 'Disturbances',
	'vname': 'Índice Normalizado de Quema', 'vname_en': 'Normalized Burn Ratio',
	'vname_fr': 'Normalized Burn Ratio', 'vname_de': 'Normalized Burn Ratio', 'minp': -0.5, 'maxp': 1,
	'pm': NBR_PALETTE, 'pg': '#7a0403',
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
DEM = {
	'type': 'Topografía', 'type_en': 'Topography', 'type_fr': 'Topography', 'type_de': 'Topography',
	'sensor': 'DEM', 'col': 'COPERNICUS/DEM/GLO30_2024_1', 'band': 'DEM', 'm': 30, 'tr': 'fixed',
	'dr': 'fixed layer, without dates (TanDEM-X, 2011-2015)', 'scale': 1, 'offset': 0, 'pg': '#8c510a',
	'large_areas': True,
	'static': True,  # without dates: maps and their statistics, no time series, trends or comparisons
	'notes': {
		'ft': 'Copernicus DEM GLO-30 (release 2024_1), from the radar of TanDEM-X (2011-2015), 30 m: a surface model, '
		      'so it gives the height of the canopy and of the buildings, not that of the ground. The slope is that of '
		      'ee.Terrain.slope, in degrees (0 = flat, 90 = vertical); on pixels more than twice as big as those of '
		      'the data, the mean of the slopes of their 30 m pixels. A fixed layer, without dates: maps, GeoTIFFs and '
		      'statistics of the region, but no time series, trends or comparisons; the period, metrics and pixel '
		      'filters do not apply.',
	},
}
TEMPLATES = {'NBR': NBR, 'RBR': dict(NBR, **RBR), 'SCF': SCF, 'ELEVATION': DEM, 'SLOPE': DEM}  # fields of EXTRA

_catalog = None


def load():
	"""The whole catalog: fields, collections (date ranges) and variables."""
	global _catalog
	if _catalog is None:
		with open(CATALOG, encoding='utf-8') as f:
			_catalog = json.load(f)
	return _catalog


def variables():
	"""Entries of the catalog, with FIXES applied, and those of EXTRA."""
	entries = [dict(e, **FIXES.get(e['ref'], {})) for e in load()['variables']]
	by_ref = {e['ref']: e for e in entries}
	extra = [dict(by_ref[base] if base is not None else {}, **dict(TEMPLATES[changes['index']], **changes), ref=ref)
	         for ref, (base, changes) in EXTRA.items() if base is None or base in by_ref]
	return entries + extra


def find(index, sensor=None, collection=None, ref=None):
	"""Entry of the catalog of a variable: by REF, or by INDEX (e.g. 'NDVI') and SENSOR ('Sentinel-2', 'Landsat',
	'Modis') and, when several collections have them (e.g. MOD13Q1 and MYD13Q1), COLLECTION. Without COLLECTION
	the first entry of the catalog is used. Names are case insensitive."""
	entries = variables()
	if ref is not None:
		for e in entries:
			if e['ref'] == int(ref):
				return e
		raise KeyError(f'no entry with ref {ref} in the catalog of MonitorEO')
	low = lambda s: str(s).lower().replace(' ', '')
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
