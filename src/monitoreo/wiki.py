"""The sections of the manual of MonitorEO (the wiki of its repository) that explain each variable, for the links that
the results give next to them (variable_links: in the answer of every computation, 'manual'), without downloading the
wiki (monitoreo.manual searches it for the assistant). The QGIS plugin takes this module in its zip.

    wiki.variable_section('NDVI')   # {'variable', 'title', 'url' (English), 'url_es' (Spanish)}
    wiki.variable_links({'variable': 'NDVI', 'where': [{'variable': 'ELEVATION', 'min': 1500}]})   # both, once each
"""

import re

WEB = 'https://github.com/monitoreo-obsnev/monitoreo/wiki/'
PAGES = ('Conceptos', 'Concepts')  # the pages (Spanish, English) with the sections of the variables


def anchor(title):
	"""The anchor of a heading in GitHub (as manual._anchor): 'NDVI: Normalized Difference Vegetation Index' ->
	'ndvi-normalized-difference-vegetation-index'."""
	return re.sub(r'[^\w\- ]', '', title.strip().lower()).replace(' ', '-')


# The section of the wiki that explains each variable (in «What each variable measures» of the pages Conceptos and
# Concepts): its heading in Spanish and in English, for the links of the results (variable_links); the data of Earth
# Engine outside the catalog, that of «Earth Engine data by its ID». tests/test_wiki_links.py checks that every
# variable of the catalog has one and that the headings are those of the wiki.
HEADINGS = {
	'NDVI': ('NDVI: índice de vegetación de diferencia normalizada', 'NDVI: Normalized Difference Vegetation Index'),
	'EVI': ('EVI: índice de vegetación mejorado', 'EVI: Enhanced Vegetation Index'),
	'LAI': ('LAI: índice de área foliar', 'LAI: Leaf Area Index'),
	'CLre': ('CLre y CLreB7: índice de clorofila del borde rojo', 'CLre and CLreB7: Red-edge Chlorophyll Index'),
	'CLreB7': ('CLre y CLreB7: índice de clorofila del borde rojo', 'CLre and CLreB7: Red-edge Chlorophyll Index'),
	'WAVI': ('WAVI: índice de vegetación ajustado al agua', 'WAVI: Water Adjusted Vegetation Index'),
	'MSAVI2': ('MSAVI2: índice de vegetación ajustado al suelo modificado',
	           'MSAVI2: Modified Soil Adjusted Vegetation Index'),
	'GPP': ('GPP y NPP: producción primaria bruta y neta', 'GPP and NPP: gross and net primary production'),
	'Chl-a': ('Chl-a: clorofila a en el agua', 'Chl-a: chlorophyll a in water'),
	'NDCI': ('NDCI: índice de clorofila de diferencia normalizada', 'NDCI: Normalized Difference Chlorophyll Index'),
	'NDWI': ('NDWI: índice de agua de diferencia normalizada', 'NDWI: Normalized Difference Water Index'),
	'LSWI': ('LSWI: índice de agua superficial terrestre', 'LSWI: Land Surface Water Index'),
	'MSI': ('MSI: índice de estrés hídrico', 'MSI: Moisture Stress Index'),
	'NDSI': ('NDSI: índice de nieve de diferencia normalizada', 'NDSI: Normalized Difference Snow Index'),
	'SCF': ('SCF: frecuencia de nieve', 'SCF: snow cover frequency'),
	'SCD': ('SCD: días de nieve', 'SCD: snow cover days'),
	'SMOD': ('SMOD: día de deshielo', 'SMOD: snow melt-out day'),
	'ET': ('ET y LE: evapotranspiración y calor latente', 'ET and LE: evapotranspiration and latent heat'),
	'LST': ('LST: temperatura de la superficie', 'LST: Land Surface Temperature'),
	'ALBEDO': ('ALBEDO', 'ALBEDO'),
	'ARSL': ('ARSL: profundidad óptica de aerosoles', 'ARSL: Aerosol Optical Depth'),
	'NBR': ('NBR y RBR: incendios', 'NBR and RBR: fires'),
	'RdNBR': ('RdNBR: dNBR relativo (incendios)', 'RdNBR: relative dNBR (fires)'),
	'BURNDATE': ('BURNDATE: fecha de quema', 'BURNDATE: burn date'),
	'ELEVATION': ('ELEVATION y SLOPE: elevación y pendiente', 'ELEVATION and SLOPE: elevation and slope'),
	'ASPECT': ('ASPECT: orientación', 'ASPECT: aspect'),
	'TWI': ('TWI: índice topográfico de humedad', 'TWI: topographic wetness index'),
	'CF': ('CF: frecuencia de nubes', 'CF: cloud frequency'),
	'CLIMATE': ('Clima: precipitación, temperatura y balance de agua',
	            'Climate: precipitation, temperature and water balance'),
	'PDSI': ('PDSI y SPEI: índices de sequía', 'PDSI and SPEI: drought indices'),
	'BIO': ('BIO01 a BIO19: variables bioclimáticas de WorldClim', 'BIO01 to BIO19: bioclimatic variables of WorldClim'),
	'ECOREGION': ('ECOREGION y BIOME: ecorregiones y biomas', 'ECOREGION and BIOME: ecoregions and biomes'),
	'DATA': ('Datos de Earth Engine por su ID', 'Earth Engine data by its ID'),
	'dNBR': ('Severidad de incendios (dNBR)', 'Burn severity (dNBR)'),  # the index of burn_severity
}
# the variables explained in the section of another one
SAME_SECTION = {'LE': 'ET', 'RBR': 'NBR', 'SLOPE': 'ELEVATION', 'BIOME': 'ECOREGION', 'NPP': 'GPP',
                **{v: 'PDSI' for v in ('SPEI1', 'SPEI3', 'SPEI6', 'SPEI12')},
                **{v: 'CLIMATE' for v in ('PRECIP', 'TMAX', 'TMIN', 'TMEAN', 'PET', 'AET', 'CWD', 'SOILM', 'VPD')},
                **{f'BIO{i:02d}': 'BIO' for i in range(1, 20)}}


def variable_section(variable):
	"""The section of the wiki of VARIABLE (a name of the catalog, e.g. 'NDVI'; None: the data of Earth Engine by
	their ID): {'variable', 'title' (its heading in English), 'url' (English), 'url_es' (Spanish)}; None for a name
	without one."""
	key = 'DATA' if not variable else SAME_SECTION.get(variable, variable)
	if key not in HEADINGS:
		return None
	es, en = HEADINGS[key]
	return {'variable': variable or 'Earth Engine data by its ID', 'title': en,
	        'url': f'{WEB}{PAGES[1]}#{anchor(en)}', 'url_es': f'{WEB}{PAGES[0]}#{anchor(es)}'}


def _conditions(where):
	"""The variables of the conditions WHERE of a call (a list of them, or one): their names, without the land cover
	masks (landcover), which are not variables."""
	if isinstance(where, dict):
		where = [where]
	return [w.get('variable') or w.get('index') for w in where or [] if isinstance(w, dict)
	        and (w.get('variable') or w.get('index'))]


def variable_links(args):
	"""The sections of the wiki of the variables of a call with the arguments ARGS (variable, or index of the burn
	severity, other_variable, the variable of its zones and those of its conditions, where; the data of Earth Engine by
	their ID, collection or image without variable, their own section), each once (see variable_section): what the
	results give next to them, so that the user can read what each variable is. [] without variables."""
	args = args if isinstance(args, dict) else {}
	names = []
	index = args.get('index')
	if args.get('variable') or (index and variable_section(index)):
		names.append(args.get('variable') or index)
	elif args.get('collection') or args.get('image'):
		names.append(None)  # data of Earth Engine by its ID
	if args.get('other_variable'):
		names.append(args['other_variable'])
	zones = args.get('zones')
	if isinstance(zones, dict) and (zones.get('variable') or zones.get('index')):
		names.append(zones.get('variable') or zones.get('index'))
	names += _conditions(args.get('where'))
	recipe = args.get('recipe')  # download_variables: the variables of its recipe (a dictionary)
	for v in (recipe.get('variables') or []) if isinstance(recipe, dict) else []:
		if isinstance(v, dict):
			names.append(v.get('variable') or v.get('index') or (None if v.get('collection') or v.get('image') else ''))
	out, seen = [], set()
	for name in names:
		link = variable_section(name) if name != '' else None
		if link and link['url'] not in seen:
			seen.add(link['url'])
			out.append(link)
	return out
