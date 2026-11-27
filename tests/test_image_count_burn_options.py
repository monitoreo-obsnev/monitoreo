"""image_count (the images and valid observations of each step, after the pixel filters), the options of burn_severity
for the fire alone in a large region (seed, largest) and for the offset of the dNBR (offset_region), and the statistic
count of a series over several steps. Offline, with Earth Engine faked; the tests marked ee compute in Earth Engine
(EE_PROJECT): the values of count over several months, a coverage that never exceeds 1, the largest patch and the
offset over a fire."""

import csv
import os

import pytest

from monitoreo import cli, fire, readme, references, report, services, timeseries


def test_which_patches_the_perimeter_keeps():
	assert fire.check_keep() is None and fire.check_keep([], False) is None
	assert fire.check_keep(largest=True) == 'largest'
	assert fire.check_keep(['-3.49', 36.98]) == [-3.49, 36.98]
	for bad in ([1], [1, 2, 3], ['a', 'b'], [200, 0], [0, 95], 'here'):
		with pytest.raises(ValueError, match='seed'):
			fire.check_keep(bad)
	with pytest.raises(ValueError, match='not both'):
		fire.check_keep([1, 2], True)


def test_seed_and_largest_need_the_perimeter():
	before, after = ('2005-06-01', '2005-09-15'), ('2005-10-01', '2005-11-30')
	for given in ({'seed': [1, 2]}, {'largest': True}):
		with pytest.raises(ValueError, match='give also perimeter'):
			services._perimeter_args('dNBR', None, None, None, 'Landsat', before, after, **given)
	out = services._perimeter_args('dNBR', 'fire.gpkg', None, None, 'Landsat', before, after, seed=[-3.49, 36.98])
	assert out['keep'] == [-3.49, 36.98]
	assert 'keep' not in services._perimeter_args('dNBR', 'fire.gpkg', None, None, 'Landsat', before, after)
	assert services._offset_answer(None) == {} and services._offset_answer(0.03) == {'offset': 0.03}


def test_the_series_has_the_coverage_without_a_minimum(monkeypatch):
	seen = []

	def table(spec, regions, step, metric, stat, scale, steps, crs, **kw):
		seen.append(kw)

		class FC:
			def getInfo(self):
				return {'features': [{'properties': {'date': s, 'n_images': 0}} for s in steps]}
		return FC()
	monkeypatch.setattr(timeseries, 'table', table)
	rows = timeseries._fetch(None, None, 'annual', 'count', 'mean', 30, ['a'], 'EPSG:32630', coverage=True)
	assert rows == [{'value': None, 'n_pixels': 0, 'coverage': 0, 'date': 'a', 'n_images': 0}]
	assert seen == [{'coverage': True}]


def test_image_count(monkeypatch, tmp_path):
	got = {}

	def series(spec, regions, step, metric, stat, scale, progress=None, steps=None, **kw):
		got.update(spec=spec, step=step, metric=metric, stat=stat, kw=kw)
		return [{'region': 'park', 'date': '1990-06-01', 'value': 4.5, 'n_pixels': 90, 'n_images': 7, 'coverage': 0.9},
		        {'region': 'park', 'date': '1991-06-01', 'value': None, 'n_pixels': 0, 'n_images': 0, 'coverage': 0}], 30
	monkeypatch.setattr(timeseries, 'series', series)
	monkeypatch.setattr(services.areas, 'region', lambda r: None)
	path = str(tmp_path / 'count.csv')
	res = services.image_count({'wdpa_id': 1}, 'NDVI', 'Landsat', '1990-01-01', '1991-12-31', season=['06-01', '09-30'],
	                           csv=path)
	assert (got['metric'], got['stat'], got['step'], got['kw']) == ('count', 'mean', 'annual', {'coverage': True})
	assert got['spec']['metric'] == 'count'
	assert res['rows'][0] == {'region': 'park', 'date': '1990-06-01', 'n_images': 7, 'observations': 4.5,
	                          'coverage': 0.9, 'n_pixels': 90}
	assert res['summary'] == [{'region': 'park', 'n_steps': 2, 'n_images': 7, 'steps_without_data': 1,
	                           'observations_min': 0, 'observations_median': 4.5, 'coverage_min': 0}]
	with open(path, encoding='utf-8') as f:
		header = next(csv.reader(f))
	assert header[:len(services.IMAGE_COUNT_COLUMNS)] == services.IMAGE_COUNT_COLUMNS
	assert 'Images and valid observations of NDVI' in res['title']


def test_image_count_is_documented():
	assert 'image_count' in references.EARTH_ENGINE
	assert 'observations' in readme.COLUMNS and 'image_count' in report.METHODS and 'image_count' in report.TABLES
	args = {'region': {'wdpa_id': 1}, 'variable': 'NDVI', 'sensor': 'Landsat', 'start': '1990-01-01',
	        'end': '1999-12-31'}
	facts = dict(report.item_facts('image_count', args, {'scale': 30}))
	assert 'Temporal metric' not in facts and facts['Step'] == report.STEPS['annual']
	facts = dict(report.item_facts('time_series', args, {'scale': 30}))
	assert 'Temporal metric' in facts


def test_the_command_line(capsys):
	with pytest.raises(SystemExit):
		cli.main(['count', '--help'])
	text = ' '.join(capsys.readouterr().out.split())
	assert text.startswith('usage: monitoreo count') and '--step' in text and '--png' in text
	with pytest.raises(SystemExit):
		cli.main(['burn', '--help'])
	text = ' '.join(capsys.readouterr().out.split())
	assert '--seed LON LAT' in text and '--largest' in text and '--offset-region JSON' in text
	with pytest.raises(SystemExit):
		cli.main(['burn', '--region', '{"bbox": [0, 0, 1, 1]}', '--start', '2020-01-01', '--end', '2020-02-01',
		          '--other-start', '2020-03-01', '--other-end', '2020-04-01', '--largest'])
	assert 'give also --perimeter' in capsys.readouterr().err


# In Earth Engine --------------------------------------------------------------------------------------------------

EE = [pytest.mark.ee, pytest.mark.skipif(not os.environ.get('EE_PROJECT'), reason='EE_PROJECT not set')]


@pytest.fixture
def ee_init():
	services.init()

BOX = {'geojson': {'type': 'Polygon', 'coordinates': [[[-0.09, 42.65], [-0.07, 42.65], [-0.07, 42.665],
                                                       [-0.09, 42.665], [-0.09, 42.65]]]}}  # the valley of Ordesa
FIRE = {'bbox': [-3.60, 36.88, -3.36, 37.06]}  # around the fire of Lanjaron of September 2005 (3,381 ha)
FIRE_PERIODS = dict(sensor='Landsat', start='2005-06-01', end='2005-09-15', other_start='2005-10-01',
                    other_end='2005-11-30')


@EE[0]
@EE[1]
def test_count_over_several_steps_and_a_coverage_of_at_most_one(ee_init):
	"""The statistic count over several months had no value (the outputs of the reducer count alone are the names
	of the bands), and the coverage of the mean could exceed 1 (it counts the pixels the region only touches)."""
	for stat in ('count', 'mean', 'median'):
		rows = services.time_series(BOX, 'NDVI', 'Sentinel-2', '2020-06-01', '2020-08-31', stat=stat,
		                            min_coverage=0.3)['rows']
		assert len(rows) == 3 and all(r['value'] is not None for r in rows), stat
		assert all(0 < r['coverage'] <= 1 for r in rows), (stat, rows)
	rows = services.time_series(BOX, 'NDVI', 'Sentinel-2', '2020-06-01', '2020-08-31', stat='count')['rows']
	assert all(r['value'] == r['n_pixels'] > 0 for r in rows)


@EE[0]
@EE[1]
def test_image_count_in_earth_engine(ee_init):
	res = services.image_count(BOX, 'NDVI', 'Landsat', '1990-01-01', '1992-12-31', season=['06-01', '09-30'])
	assert [r['date'] for r in res['rows']] == ['1990-06-01', '1991-06-01', '1992-06-01']
	for r in res['rows']:
		assert r['n_images'] >= r['observations'] > 0 and 0 < r['coverage'] <= 1
	assert 'LANDSAT/LT05' in res['data_source']


@EE[0]
@EE[1]
def test_the_fire_alone_and_its_offset(ee_init, tmp_path):
	whole = services.burn_severity(FIRE, perimeter=str(tmp_path / 'all.gpkg'), **FIRE_PERIODS)
	largest = services.burn_severity(FIRE, perimeter=str(tmp_path / 'largest.gpkg'), largest=True, **FIRE_PERIODS)
	seed = services.burn_severity(FIRE, perimeter=str(tmp_path / 'seed.gpkg'), seed=[-3.486, 36.977], **FIRE_PERIODS)
	assert whole['perimeter_patches']['bbox'] > 10
	assert largest['perimeter_patches']['bbox'] == seed['perimeter_patches']['bbox'] == 1
	assert largest['perimeter_ha'] == seed['perimeter_ha']  # the point is in the largest patch, the fire
	assert 3000 < largest['perimeter_ha']['bbox'] < whole['perimeter_ha']['bbox']
	assert largest['classes'] == whole['classes']  # the classes are those of the whole region
	ring = {'bbox': [-3.56, 36.90, -3.54, 36.92]}  # unburned land west of the fire
	shifted = services.burn_severity(ring, offset_region=ring, index='RdNBR', **FIRE_PERIODS)
	assert shifted['offset'] is not None and abs(shifted['stats'][0]['median']) < 0.02
	assert os.path.basename(largest['perimeter']) == 'largest.gpkg'
	inside = {'bbox': [-3.50, 36.95, -3.45, 37.00]}  # in the fire: the offset of the ring, outside this region
	for index in ('dNBR', 'RBR', 'RdNBR'):
		res = services.burn_severity(inside, offset_region=ring, index=index, **FIRE_PERIODS)
		assert res['offset'] == pytest.approx(shifted['offset']), index
	with pytest.raises(ValueError, match='offset_region has no pixel'):
		services.burn_severity(FIRE, offset_region={'bbox': [10, 10, 10.001, 10.001]}, **FIRE_PERIODS)


def test_the_offset_and_the_patch_in_the_readme_and_the_references():
	args = {'region': {'bbox': [-3.6, 36.88, -3.36, 37.06]}, 'sensor': 'Landsat', 'start': '2005-06-01',
	        'end': '2005-09-15', 'other_start': '2005-10-01', 'other_end': '2005-11-30', 'index': 'RdNBR',
	        'offset_region': {'wdpa_id': 555513}}
	result = {'scale': 30, 'offset': 0.0274, 'perimeter': 'fire.gpkg', 'perimeter_ha': {'bbox': 3957.5},
	          'perimeter_kept': 'the largest burned patch', 'burned_ha': {'bbox': 4000.0}}
	facts = dict(report.item_facts('burn_severity', args, result))
	assert facts['Offset of the dNBR'].startswith('0.0274, the median dNBR of the offset region')
	assert facts['Perimeter of the burned area'].endswith('; only the largest burned patch')
	assert 'unless an offset region gives it' in report.METHODS['burn_severity_rdnbr']
	ids = [r['id'] for r in references.cite('burn_severity', dict(args, index='dNBR'))['references']]
	assert {'miller2007', 'parks2014', 'wdpa'} <= set(ids)  # the offset, and the protected area that gives it
	ids = [r['id'] for r in references.cite('burn_severity', dict(args, index='dNBR', offset_region=None))['references']]
	assert 'parks2014' not in ids and 'wdpa' not in ids
	assert 'Offset of the dNBR' not in dict(report.item_facts('burn_severity', dict(args, offset_region=None),
	                                                           dict(result, offset=None)))
