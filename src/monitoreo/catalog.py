"""Catalog of variables of MonitorEO (catalog.json, made by tools/import_catalog.py)."""

import json
import os

CATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'catalog.json')

# Corrections of entries of MonitorEO, applied when an entry is read (catalog.json keeps the values of the app):
# ref: {field: value}
FIXES = {
	32: {'scale': 0.1},  # Lai of MCD15A3H has a scale of 0.1 (raw 58 = 5.8 m2/m2 in the Amazon rain forest), not 0.01
}

# Variables that MonitorEO-OBSNEV adds to those of the app: {ref: (entry of the app it copies, changes)}. Their refs
# start at 101, so that they never collide with the entries of the app.
NBR_PALETTE = ['7a0403', 'c0392b', 'e67e22', 'f5cba7', 'f2efe6', 'b8e186', '7fbc41', '4d9221', '276419']
EXTRA = {
	101: (3, {'index': 'NBR', 'ft': 'N(nir,swir2)', 'f': '(SR_B5 - SR_B7) / (SR_B5 + SR_B7)'}),  # Landsat
	102: (4, {'index': 'NBR', 'ft': 'N(B8,B12)', 'f': '(B8 - B12) / (B8 + B12)'}),  # Sentinel-2
}
NBR = {
	'type': 'Perturbaciones', 'type_en': 'Disturbances', 'type_fr': 'Disturbances', 'type_de': 'Disturbances',
	'vname': 'Índice Normalizado de Quema', 'vname_en': 'Normalized Burn Ratio',
	'vname_fr': 'Normalized Burn Ratio', 'vname_de': 'Normalized Burn Ratio', 'minp': -0.5, 'maxp': 1,
	'pm': NBR_PALETTE, 'pg': '#7a0403',
	'notes': {'f': 'Burn severity: dNBR = NBR before - NBR after the fire (compare_series or download_comparison give '
	               'after - before, that is -dNBR); dNBR > 0.1 burned (Key & Benson 2006).'},
}

_catalog = None


def load():
	"""The whole catalog: source, fields, collections (date ranges) and variables."""
	global _catalog
	if _catalog is None:
		with open(CATALOG, encoding='utf-8') as f:
			_catalog = json.load(f)
	return _catalog


def variables():
	"""Entries of the catalog, with FIXES applied, and those of EXTRA."""
	app = [dict(e, **FIXES.get(e['ref'], {})) for e in load()['variables']]
	by_ref = {e['ref']: e for e in app}
	extra = [dict(by_ref[base], **NBR, **changes, ref=ref) for ref, (base, changes) in EXTRA.items() if base in by_ref]
	return app + extra


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
