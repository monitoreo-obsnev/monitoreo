"""Download of a recipe of variables as GeoTIFFs on aligned grids, over a study area and, optionally, over the
ecoregions of RESOLVE Ecoregions 2017 that it touches (their union if several), each grid with its own pixel size:
the input variables of a model, such as those of eHabitat+.

A recipe is a dictionary, or a YAML file, with the grids and the variables:

    project: my-project                # Earth Engine project (default: EE_PROJECT)
    crs: auto                          # CRS of the grids: auto = WGS 84 / UTM of the centre of the study area
    study: {resolution: 10, buffer: 0, drive: false}
    ecoregion: {resolution: 100, crs: null, drive: true}     # optional; crs null = that of the study area
    drive_folder: MonitorEO            # folder of Google Drive of the export tasks (grids with drive: true)
    drive_dir: null                    # local copy of that folder (default: in Google Drive for desktop)
    period: ['2018-01-01', '2021-12-31']   # options of every variable (see monitoreo.variable)
    quality: {clouds: true, water: true, snow: true, aerosols: true, cloud_score: 0.6}
    variables:
      - {index: NDVI, sensor: Sentinel-2, metric: [p95, p5]}  # a file per metric
      - {name: slope, image: COPERNICUS/DEM/GLO30_2024_1, band: DEM, terrain: slope}

The study grid covers the rectangle of the study area grown by buffer metres and 2 pixels; the ecoregion grid, the
rectangle of the ecoregions, with NoData outside them. Their edges are multiples of the pixel size. The files of
the study grid go to a folder and those of the ecoregion grid to its subfolder 'ecoregion' (with the polygons of
the ecoregions in ecoregions.gpkg): float32 GeoTIFFs with NoData -9999, numbered in the order of the recipe
(1_NDVI_S2_p95.tif, 2_NDVI_S2_p5.tif, ...). A record in each folder (monitoreo.json) keeps what every file was made
with, so running the recipe again downloads only the files whose variable or grid changed.

A grid is downloaded directly, in tiles computed by Earth Engine on demand (grid.download), or, with drive: true, by
export tasks to Google Drive (drive.export), without limits of size or time per tile, whose files are imported from
the local copy of Google Drive when they finish. Running the recipe again does not start the tasks again: it waits
for them (or, with wait=False, imports those already finished).

    from monitoreo import recipe, services
    services.init('my-project')
    plan = recipe.plan('variables.yaml', 'area.gpkg')
    recipe.run(plan, 'out', log=print)
"""

import datetime
import json
import os
import re
import time

from . import areas, catalog, drive, sensors
from . import variable as variables
from .grid import Grid, download

RECORD = 'monitoreo.json'
ECO_FOLDER = 'ecoregion'
MARGIN_PIXELS = 2
GRIDS = ('study', 'ecoregion')
KEYS = {'project', 'crs', 'study', 'ecoregion', 'variables', 'drive_folder', 'drive_dir'} | (variables.KEYS - {
	'name', 'index', 'sensor', 'collection', 'ref', 'image', 'band', 'scale', 'offset', 'terrain', 'metric', 'metrics'})


def _quiet(*args, **kwargs):
	pass


# Recipe ------------------------------------------------------------------------------------------------------------

def read(recipe, extra=()):
	"""The recipe RECIPE (a dictionary or the path of a YAML file), checked. EXTRA: other keys allowed (those of the
	tool that reads the recipe)."""
	if not isinstance(recipe, dict):
		import yaml
		path = recipe
		try:
			with open(path, encoding='utf-8') as f:
				recipe = yaml.safe_load(f) or {}
		except OSError as e:
			raise ValueError(f'cannot read the recipe {path}: {e}') from e
		except yaml.YAMLError as e:
			raise ValueError(f'{path} is not valid YAML: {e}') from e
		if not isinstance(recipe, dict):
			raise ValueError(f'{path} is not a recipe (a dictionary of options)')
	unknown = set(recipe) - KEYS - set(extra)
	if unknown:
		raise ValueError(f"unknown keys in the recipe: {', '.join(sorted(unknown))}")
	if not recipe.get('variables'):
		raise ValueError('the recipe has no variables')
	return recipe


def expand(recipe, warn=_quiet):
	"""Specs of the files of RECIPE, in order, with the file name (numbered) in 'file'. WARN(message) gets the pixel
	filters that remove what a variable measures."""
	defaults = {k: v for k, v in recipe.items() if k in variables.KEYS}
	out = []
	for i, var in enumerate(recipe['variables'], 1):
		if not isinstance(var, dict):
			raise ValueError(f'variable {i} of the recipe is not a dictionary of options')
		try:
			new = variables.specs(var, defaults)
			for s in new:
				if variables.kind(s) == 'catalog':
					entry = variables.entry_of(s)
					for f in sensors.conflicts(entry, s['quality']):
						warn(f"WARNING: the {f} filter removes what {entry['index']} measures: "
						     f"give this variable quality: {{{f}: false}}")
		except (ValueError, KeyError) as e:
			raise ValueError(f'variable {i} of the recipe: ' + str(e).strip('"')) from e
		out += new
	width = len(str(len(out))) if len(out) >= 10 else 1
	names = set()
	for i, s in enumerate(out, 1):
		if s['name'] in names:
			raise ValueError(f"two variables give the file name {s['name']}: give them different names (name:)")
		names.add(s['name'])
		s['file'] = f"{i:0{width}d}_{s['name']}.tif"
	return out


# Grids -------------------------------------------------------------------------------------------------------------

class Plan:
	"""What a recipe downloads: the recipe, the specs of its files, its grids ({'study': Grid, 'ecoregion': Grid})
	and the ecoregions (ee.FeatureCollection in eco, their properties in ecoregions)."""

	def __init__(self, recipe, specs, grids, area, eco=None, ecoregions=None):
		self.recipe, self.specs, self.grids, self.area = recipe, specs, grids, area
		self.eco, self.ecoregions = eco, ecoregions or []

	def summary(self):
		"""Plain description: area, grids (with pixels and MB per variable), ecoregions and files with their pixel
		filters."""
		files = []
		for s in self.specs:
			f = {'file': s['file']}
			if variables.kind(s) == 'catalog':
				f['pixel_filters'] = [k for k, v in sensors.filters(variables.entry_of(s), s['quality']).items() if v]
			files.append(f)
		return {'area': self.area,
		        'grids': {n: dict(g.describe(), pixels=g.pixels, mb_per_variable=round(g.pixels * 4 / 2 ** 20, 2))
		                  for n, g in self.grids.items()},
		        'ecoregions': self.ecoregions, 'files': files}


def _study_area(area, layer, res, crs):
	"""(Earth Engine geometry, CRS, (xmin, ymin, xmax, ymax) in that CRS, name) of the study AREA: a vector file
	(LAYER) or a region of areas.region."""
	if isinstance(area, dict):
		geom = areas.region(area).geometry()
		if crs == 'auto':
			crs = areas.utm_of(*geom.centroid(1).coordinates().getInfo())
		ring = geom.bounds(res / 2, crs).getInfo()['coordinates'][0]
		xs, ys = [p[0] for p in ring], [p[1] for p in ring]
		return geom, crs, (min(xs), min(ys), max(xs), max(ys)), json.dumps(area)
	path = os.fspath(area)
	geom, srs = areas.read_vector(path, layer)
	if crs == 'auto':
		crs = areas.utm_crs(geom, srs)
	ee_geom = areas.to_ee(geom, srs, simplify=res if srs.IsProjected() else None)
	return ee_geom, crs, areas.bounds(geom, srs, crs), os.path.basename(path)


def plan(recipe, area, layer=None, buffer=None, only=None, extra=(), warn=_quiet):
	"""Plan of RECIPE (dictionary or YAML file) over the study AREA: a vector file (and its LAYER) or a region of
	areas.region, e.g. {'wdpa_id': 555513}. BUFFER: metres around the study area when the recipe has no study:
	buffer (default 0). ONLY: 'study' or 'ecoregion' for one of the grids. Needs Earth Engine (services.init)."""
	recipe = read(recipe, extra)
	specs = expand(recipe, warn)
	study = recipe.get('study') or {}
	eco_opts = recipe.get('ecoregion') or {}
	if only not in (None,) + GRIDS:
		raise ValueError(f"only: {only}? Use {' or '.join(GRIDS)}")
	if not study.get('resolution'):
		raise ValueError('give the pixel size of the study area (study: resolution) in the recipe')
	res = float(study['resolution'])
	buffer = float(study['buffer'] if study.get('buffer') is not None else buffer or 0)
	crs = str(recipe.get('crs') or 'auto')
	geom, crs, box, name = _study_area(area, layer, res, 'auto' if crs.lower() == 'auto' else crs)
	grids = {'study': Grid.around(crs, res, *box, margin=buffer + MARGIN_PIXELS * res)}
	eco = info = None
	if eco_opts.get('resolution') and only != 'study':
		eco_res = float(eco_opts['resolution'])
		eco_crs = str(eco_opts.get('crs') or crs)
		eco = areas.ecoregions(geom)
		info = [e['properties'] for e in areas.ecoregion_info(eco)]
		if not info:
			raise ValueError('the study area is not in any ecoregion of RESOLVE Ecoregions 2017')
		grids['ecoregion'] = Grid.around(eco_crs, eco_res, *areas.ecoregion_bounds(eco, eco_crs, eco_res / 2))
	if only == 'ecoregion':
		if 'ecoregion' not in grids:
			raise ValueError('the recipe has no ecoregion: resolution')
		del grids['study']
	return Plan(recipe, specs, grids, name, eco, info)


def n_images(p):
	"""{file: number of images of its period over the study area (None for a fixed image, or the error)}."""
	region = p.grids.get('study', next(iter(p.grids.values()))).region()
	out = {}
	for s in p.specs:
		try:
			out[s['file']] = variables.n_images(s, region)
		except Exception as e:
			out[s['file']] = f'ERROR: {e}'
	return out


# Downloads ---------------------------------------------------------------------------------------------------------

def folders(folder):
	"""{grid: folder of its files}."""
	return {'study': folder, 'ecoregion': os.path.join(folder, ECO_FOLDER)}


def load_record(folder, record=RECORD):
	try:
		with open(os.path.join(folder, record), encoding='utf-8') as f:
			return json.load(f)
	except (OSError, ValueError):
		return {}


def save_record(folder, rec, record=RECORD):
	path = os.path.join(folder, record)
	with open(path + '.tmp', 'w', encoding='utf-8') as f:
		json.dump(rec, f, indent=1, ensure_ascii=False, default=str)
	os.replace(path + '.tmp', path)


def spec_key(spec):
	"""What defines a file: its spec (without the file name) as JSON."""
	return json.loads(json.dumps({k: v for k, v in spec.items() if k != 'file'}, sort_keys=True, default=str))


def _now():
	return datetime.datetime.now().isoformat(timespec='seconds')


def local_drive_dir(drive_folder, drive_dir=None):
	"""Local folder of the files exported to DRIVE_FOLDER: DRIVE_DIR, or that folder in Google Drive for desktop
	(None if it is not installed)."""
	if drive_dir:
		return drive_dir
	found = drive.local_drives()
	if len(found) > 1:
		raise ValueError(f"several Google Drive folders on this computer ({', '.join(found)}): give the folder of the "
		                 'exported files (drive_dir)')
	return os.path.join(found[0], drive_folder) if found else None


def run(p, folder, record=RECORD, overwrite=False, drive_all=False, drive_dir=None, prefix=None, wait=True,
        tile=512, workers=8, project=None, log=_quiet, progress=None):
	"""Download the files of the plan P to FOLDER (and FOLDER/ecoregion). Files up to date in the RECORD of their
	folder are kept unless OVERWRITE. The grids with drive: true in the recipe (all with DRIVE_ALL) are exported to
	drive_folder of Google Drive, as <PREFIX><grid>_<file> (PREFIX: the name of FOLDER and _), and imported from
	DRIVE_DIR (default: drive_dir of the recipe, or Google Drive for desktop); WAIT: wait for the tasks (else import
	those already finished). TILE, WORKERS: tiles of the direct downloads. LOG(message) gets what happens and
	PROGRESS(file, done tiles, total tiles) the progress of the direct downloads.
	Returns {'done': all the files are there, 'folders', 'files': {grid: [files]}, 'pending': [[grid, file]] (tasks
	running), 'in_drive': [[grid, file]] (exported, not found locally), 'failed': [[grid, file, error]]}."""
	recipe = p.recipe
	dirs = folders(folder)
	prefix = re.sub(r'[^A-Za-z0-9_-]', '_', os.path.basename(os.path.normpath(folder))) + '_' if prefix is None else prefix
	via_drive = {n: drive_all or bool((recipe.get(n) or {}).get('drive')) for n in p.grids}
	drive_folder = re.sub(r'[^A-Za-z0-9_-]', '_', str(recipe.get('drive_folder') or 'MonitorEO'))
	local = local_drive_dir(drive_folder, drive_dir or recipe.get('drive_dir')) if any(via_drive.values()) else None
	recs, pending = {}, []
	for name, g in p.grids.items():
		outdir = dirs[name]
		os.makedirs(outdir, exist_ok=True)
		rec = recs[name] = load_record(outdir, record)
		rec['grid'] = g.describe()
		rec['study_area'] = p.area
		rec['catalog'] = catalog.load()['source']
		if name == 'ecoregion':
			rec['ecoregions'] = p.ecoregions
			areas.save_ecoregions(p.eco, os.path.join(outdir, 'ecoregions.gpkg'), g.res / 2)
		files = rec.setdefault('files', {})
		tasks = rec.setdefault('tasks', {})
		region = g.region()
		log(f"\n{'Study area' if name == 'study' else 'Ecoregions'} ({g.res:g} m"
		    f"{', export to Google Drive/' + drive_folder if via_drive[name] else ''}):")
		for s in p.specs:
			f = s['file']
			path = os.path.join(outdir, f)
			key = spec_key(s)
			old = files.get(f, {})
			if not overwrite and os.path.exists(path) and old.get('spec') == key and old.get('grid') == rec['grid']:
				log(f'  {f}: up to date')
				continue
			task = tasks.get(f)
			if (via_drive[name] and not overwrite and task and task['spec'] == key and task['grid'] == rec['grid']
			        and drive.status(task['operation'])[0] not in drive.FAILED):
				log(f'  {f}: export task already started')
				pending.append((name, f))
				continue
			img = variables.image(s, region, g.res)
			if name == 'ecoregion':
				img = img.clipToCollection(p.eco)
			desc = variables.describe(s)
			n = variables.n_images(s, region)
			if n == 0:
				log(f'  WARNING: {f}: no images in the period; the file will be all NoData')
			if via_drive[name]:
				drive_name = f'{prefix}{name}_{os.path.splitext(f)[0]}'
				tasks[f] = {'spec': key, 'grid': rec['grid'], 'source': desc, 'images': n,
				            'operation': drive.export(img, g, drive_name, drive_folder, project),
				            'drive_folder': drive_folder, 'drive_name': drive_name, 'started': _now()}
				save_record(outdir, rec, record)
				log(f'  {f}: export task started (Google Drive/{drive_folder}/{drive_name}.tif)')
				pending.append((name, f))
				continue
			if not progress:
				n_tiles = len(g.tiles(tile))
				log(f"  {f}: downloading ({n_tiles} tile{'s' if n_tiles > 1 else ''})")
			try:
				download(img, g, path, tile=tile, workers=workers,
				         progress=(lambda done, total, f=f: progress(f, done, total)) if progress else None,
				         metadata={'source': 'Google Earth Engine', 'monitoreo': json.dumps(desc, default=str)})
			except Exception as e:
				save_record(outdir, rec, record)
				raise RuntimeError(f'{f}: {e}') from e
			files[f] = {'spec': key, 'grid': rec['grid'], 'source': desc, 'images': n, 'downloaded': _now()}
			tasks.pop(f, None)
			save_record(outdir, rec, record)
		# files no longer in the recipe stay on disk: say so, since a model reading the folder would use them
		for f in files:
			if f not in {s['file'] for s in p.specs} and os.path.exists(os.path.join(outdir, f)):
				log(f'  WARNING: {f} is not in the recipe any more: remove it if it should not be used')
	in_drive, failed = [], []
	if pending:
		pending, in_drive, failed = import_exports(pending, recs, p.grids, dirs, local, record, wait, log)
	return {'done': not (pending or in_drive or failed), 'folders': {n: dirs[n] for n in p.grids},
	        'files': {n: [s['file'] for s in p.specs] for n in p.grids},
	        'pending': [list(x) for x in pending], 'in_drive': in_drive, 'failed': failed}


def import_exports(pending, recs, grids, dirs, local, record=RECORD, wait=True, log=_quiet, every=30):
	"""Import the files of the export tasks of PENDING ([(grid, file)]) from the local folder LOCAL (Google Drive for
	desktop, or where they were downloaded) when they finish, checking them every EVERY seconds while WAIT (else
	once). Returns (tasks still running, [grid, file] exported but not found in LOCAL, [grid, file, error] failed)."""
	log(f"\nExport tasks (also in the Tasks tab of the Code Editor); files read from {local or 'your Google Drive'}."
	    + ('\nCtrl+C stops waiting, not the tasks: run the same command again to go on.' if wait else ''))
	shown, sizes, in_drive, failed = {}, {}, [], []
	pending = list(pending)
	while pending:
		for name, f in list(pending):
			rec, outdir = recs[name], dirs[name]
			t = rec['tasks'][f]
			state, progress, error = drive.status(t['operation'])
			msg = None
			if state in drive.FAILED:
				msg = f'{state.lower()}: {error}'
				failed.append([name, f, error])
				pending.remove((name, f))
			elif state != drive.DONE:
				msg = f'{state.lower()} {progress:.0%}' if progress else state.lower()
			elif not local or not os.path.isdir(local):
				msg = f"exported to Google Drive/{t['drive_folder']}/{t['drive_name']}*.tif"
				in_drive.append([name, f])
				pending.remove((name, f))
			else:
				found = drive.find(local, t['drive_name'])
				now = [os.path.getsize(x) for x in found]
				if len(found) < drive.pieces(grids[name]) or sizes.get(f) != now:
					sizes[f] = now
					msg = 'exported, waiting for Google Drive to copy it to this computer'
				else:
					drive.mosaic(found, grids[name], os.path.join(outdir, f), metadata={
						'source': 'Google Earth Engine', 'monitoreo': json.dumps(t['source'], default=str)})
					rec['files'][f] = {k: t[k] for k in ('spec', 'grid', 'source', 'images')}
					rec['files'][f].update({'downloaded': _now(), 'via': f"Google Drive/{t['drive_folder']}"})
					del rec['tasks'][f]
					save_record(outdir, rec, record)
					msg = f"imported ({', '.join(os.path.basename(x) for x in found)})"
					pending.remove((name, f))
			if msg and shown.get(f) != msg:
				log(f'  {f}: {msg}')
				shown[f] = msg
		if not pending or not wait:
			break
		try:
			time.sleep(every)
		except KeyboardInterrupt:
			log('\nStopped waiting.')
			break
	if pending:
		log('The export tasks go on in Earth Engine: run the same command again to import their files when done.')
	if in_drive:
		log('Download the folder of the exported files from your Google Drive and run the same command with its local '
		    'folder (drive_dir) to import them.')
	return pending, in_drive, failed
