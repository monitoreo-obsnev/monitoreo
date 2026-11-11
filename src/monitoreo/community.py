"""The datasets of the GEE Community Catalog (https://gee-community-catalog.org), by its themes: images and collections
of images shared as public Earth Engine assets by the community of Earth Engine (projects/sat-io/open-datasets/...
and others), which MonitorEO computes like any data of Earth Engine given by its ID (see monitoreo.assets).

MonitorEO keeps a copy of its index (community.json, the images and collections of images of community_datasets.json
of https://github.com/samapriya/awesome-gee-community-datasets, licence CC BY 4.0, without the tables, which are not
rasters, and without the datasets of its "Insiders only" theme, which are not public), so that every tool lists them
without the internet. Its maintainers refresh it with:

    python -m monitoreo.community

Each record has id (the ID of its Earth Engine asset), title, type (image or image_collection), theme (its
thematic_group in the catalog), provider, license (and license_text when it is custom), tags and docs (its page in the
catalog, with how to cite it). The index has no bands, units, scale or DOI: monitoreo.assets.describe reads its bands
from Earth Engine, and its page says how to cite it.

References:
    Roy, S., Majumdar, S., & Swetnam, T. (2026). A community data commons for equitable Earth Science.
    https://doi.org/10.31223/X5WN4J
    Roy, S., Majumdar, S., & Swetnam, T. (2026). samapriya/awesome-gee-community-datasets: Community Catalog
    [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.7144933
"""

import datetime as dt
import json
import os

SNAPSHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'community.json')
REPOSITORY = 'samapriya/awesome-gee-community-datasets'
SOURCE = f'https://raw.githubusercontent.com/{REPOSITORY}/{{commit}}/community_datasets.json'
SITE = 'https://gee-community-catalog.org'
LICENCE = 'CC BY 4.0'
REFERENCES = ['roy2026', 'roy2026catalog']  # in catalog.json: the paper of the catalog and its releases in Zenodo
RASTERS = ('image', 'image_collection')
NOT_PUBLIC = 'Insiders only datasets'  # only for the members of its insiders program
FIELDS = ('id', 'title', 'type', 'theme', 'provider', 'license', 'license_text', 'tags', 'docs')
# The themes of the catalog (thematic_group), in the order of its site, with their names in Spanish
THEMES = [
	('Population & Socioeconomic', 'Población y socioeconomía'),
	('Geophysical, Biological & Biogeochemical', 'Geofísica, biología y biogeoquímica'),
	('Elevation and Bathymetry', 'Elevación y batimetría'),
	('Terrain and Topography', 'Relieve y topografía'),
	('Soil Properties', 'Propiedades del suelo'),
	('Global Land Use and Land Cover', 'Usos y cubiertas del suelo globales'),
	('Regional Land Use and Land Cover', 'Usos y cubiertas del suelo regionales'),
	('Hydrology', 'Hidrología'),
	('Oceans and Shorelines', 'Océanos y costas'),
	('Agriculture, Vegetation and Forestry', 'Agricultura, vegetación y bosques'),
	('Analysis Ready Data', 'Datos listos para el análisis'),
	('Global Utilities, Assets and Amenities Layers', 'Infraestructuras y servicios globales'),
	('Biodiversity, Ecosystems & Habitat Layers', 'Biodiversidad, ecosistemas y hábitats'),
	('Weather and Climate Layers', 'Tiempo y clima'),
	('Global Events Layers', 'Eventos globales'),
	('Disaster Response', 'Respuesta a desastres'),
	('Fire Monitoring and Analysis', 'Seguimiento y análisis de incendios'),
]
SPANISH = dict(THEMES)

_snapshot = None


def load():
	"""The copy of the index: {'source', 'commit', 'date', 'downloaded', 'licence', 'themes', 'datasets'}."""
	global _snapshot
	if _snapshot is None:
		with open(SNAPSHOT, encoding='utf-8') as f:
			_snapshot = json.load(f)
	return _snapshot


def _low(text):
	return str(text or '').strip().lower()


def theme_name(theme, lang='en'):
	"""The name of THEME (as in the catalog) in LANG ('en' or 'es')."""
	return SPANISH.get(theme, theme) if lang == 'es' else theme


def _theme(theme):
	"""The theme of the catalog named THEME (in English or in Spanish, case insensitive)."""
	low = _low(theme)
	for en, es in THEMES:
		if low in (_low(en), _low(es)):
			return en
	found = [en for en, es in THEMES if low and (low in _low(en) or low in _low(es))]
	if len(found) == 1:
		return found[0]
	raise ValueError(f"unknown theme {theme} of the GEE Community Catalog: use one of {'; '.join(t for t, _ in THEMES)}")


def themes(lang='en'):
	"""The themes of the catalog with images or collections of images: [{'theme' (its name in the catalog), 'name' (in
	LANG), 'datasets' (how many)}]."""
	counts = {}
	for d in load()['datasets']:
		counts[d['theme']] = counts.get(d['theme'], 0) + 1
	return [{'theme': en, 'name': theme_name(en, lang), 'datasets': counts[en]} for en, _ in THEMES if counts.get(en)]


def datasets(theme=None, text=None, kind=None, limit=None):
	"""The images and collections of images of the catalog: [{id, title, type, theme, provider, license, docs, ...}],
	optionally of one THEME (see themes), with TEXT in their title, ID, provider or tags, and of one KIND ('image' or
	'image_collection'), at most LIMIT."""
	wanted = _theme(theme) if theme else None
	if kind and kind not in RASTERS:
		raise ValueError(f"unknown kind {kind}: use image or image_collection")
	words = _low(text).split()
	out = []
	for d in load()['datasets']:
		if (wanted and d['theme'] != wanted) or (kind and d['type'] != kind):
			continue
		if words:
			hay = _low(' '.join(str(d.get(k) or '') for k in ('title', 'id', 'provider', 'tags')))
			if not all(w in hay for w in words):
				continue
		out.append(dict(d))
		if limit and len(out) >= int(limit):
			break
	return out


def record(asset):
	"""The record of the Earth Engine asset ASSET in the catalog, or None."""
	legacy = 'projects/earthengine-legacy/assets/'  # the same assets, with the prefix of the old API or without it
	asset = str(asset or '').strip().replace(legacy, '')
	for d in load()['datasets']:
		if asset == d['id'].replace(legacy, ''):
			return dict(d)
	return None


def _clean(d):
	"""The record of the copy of an entry D of community_datasets.json."""
	out = {'id': d['id'].strip(), 'title': ' '.join(str(d.get('title') or '').split()),
	       'type': d['type'], 'theme': (d.get('thematic_group') or '').strip(),
	       'provider': ' '.join(str(d.get('provider') or '').split()).strip(' ,'),
	       'license': (d.get('license') or '').strip(), 'tags': ', '.join(t.strip() for t in str(d.get('tags') or '')
	                                                                      .split(',') if t.strip()),
	       'docs': (d.get('docs') or '').strip()}
	text = str(d.get('license_text') or '').strip()
	if text and text.upper() != 'NA':
		out['license_text'] = ' '.join(text.split())
	return {k: out[k] for k in FIELDS if out.get(k)}


def update(commit=None, path=SNAPSHOT):
	"""Download community_datasets.json of COMMIT (default: the last one that changed it) and write the copy of
	MonitorEO to PATH: its images and collections of images, without those of NOT_PUBLIC. Returns how many it kept."""
	import requests
	if not commit:
		r = requests.get(f'https://api.github.com/repos/{REPOSITORY}/commits',
		                 params={'path': 'community_datasets.json', 'per_page': 1}, timeout=30)
		r.raise_for_status()
		last = r.json()[0]
		commit, date = last['sha'], last['commit']['committer']['date'][:10]
	else:
		date = None
	r = requests.get(SOURCE.format(commit=commit), timeout=60)
	r.raise_for_status()
	seen, kept = set(), []
	for d in r.json():
		if d.get('type') not in RASTERS or (d.get('thematic_group') or '').strip() == NOT_PUBLIC:
			continue
		rec = _clean(d)
		if rec['id'] in seen:
			continue
		seen.add(rec['id'])
		kept.append(rec)
	unknown = {d['theme'] for d in kept} - set(SPANISH)
	if unknown:
		raise ValueError(f"themes of the catalog that MonitorEO does not know: {', '.join(sorted(unknown))}: add them "
		                 'to monitoreo.community.THEMES')
	order = {en: i for i, (en, _) in enumerate(THEMES)}
	kept.sort(key=lambda d: (order[d['theme']], d['title'].lower(), d['id']))
	data = {'source': f'https://github.com/{REPOSITORY}', 'file': 'community_datasets.json', 'commit': commit,
	        'date': date, 'downloaded': dt.date.today().isoformat(), 'licence': LICENCE, 'site': SITE,
	        'note': 'The images and collections of images of the index of the GEE Community Catalog, without its '
	                'tables and its insiders-only datasets, as MonitorEO lists them (monitoreo.community).',
	        'datasets': kept}
	with open(path, 'w', encoding='utf-8') as f:
		json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
		f.write('\n')
	global _snapshot
	_snapshot = None
	return len(kept)


if __name__ == '__main__':
	print(f'{update()} images and collections of images of the GEE Community Catalog in {SNAPSHOT}')
