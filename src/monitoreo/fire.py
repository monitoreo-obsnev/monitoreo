"""Burn severity of a fire from the NBR (Normalized Burn Ratio, catalog entries 101 Landsat and 102 Sentinel-2):
dNBR = NBR before - NBR after the fire, classified with the scale of the USGS (Key & Benson 2006, Landscape
Assessment, FIREMON; https://www.fs.usda.gov/rm/pubs_series/rmrs/gtr/rmrs_gtr164/rmrs_gtr164_13_land_assess.pdf).
Or the RBR (Relativized Burn Ratio, Parks et al. 2014; catalog entries 103 Sentinel-2 and 104 Landsat, as computed by
Silva-Cardoza et al. 2022, https://doi.org/10.3390/rs14133122): dNBR / (NBR before + 1.001), a continuous index.
Or the RdNBR (relative dNBR, Miller & Thode 2007, https://doi.org/10.1016/j.rse.2006.12.006; catalog entries 144
Sentinel-2, 145 Landsat, 146 MODIS Terra and 147 MODIS Aqua): dNBR / sqrt(|NBR before|), with |NBR before| at least
0.001 (Howe et al. 2022), classified with the thresholds of the article (its Table 4).

The NBR before and after are the METRIC (the median by default) of the images of a period before and of a period
after the fire, with the pixel filters of MonitorEO (clouds, shadows, water, snow).

References (monitoreo.references gives them, with those of the data, with each result):
    García, M. J. L., & Caselles, V. (1991). Mapping burns and natural reforestation using Thematic Mapper data.
      Geocarto International, 6(1), 31–37. https://doi.org/10.1080/10106049109354290
    Howe, A. A., Parks, S. A., Harvey, B. J., Saberi, S. J., Lutz, J. A., & Yocom, L. L. (2022). Comparing
      Sentinel-2 and Landsat 8 for burn severity mapping in Western North America. Remote Sensing, 14(20), 5249.
      https://doi.org/10.3390/rs14205249
    Key, C. H., & Benson, N. C. (2006). Landscape assessment (LA): Sampling and analysis methods. In D. C. Lutes, R.
      E. Keane, J. F. Caratti, C. H. Key, N. C. Benson, S. Sutherland, & L. J. Gangi (Eds.), FIREMON: Fire effects
      monitoring and inventory system (Gen. Tech. Rep. RMRS-GTR-164-CD, pp. LA-1–LA-55). USDA Forest Service, Rocky
      Mountain Research Station.
      https://www.fs.usda.gov/rm/pubs_series/rmrs/gtr/rmrs_gtr164/rmrs_gtr164_13_land_assess.pdf
    Miller, J. D., & Thode, A. E. (2007). Quantifying burn severity in a heterogeneous landscape with a relative
      version of the delta Normalized Burn Ratio (dNBR). Remote Sensing of Environment, 109(1), 66–80.
      https://doi.org/10.1016/j.rse.2006.12.006
    Parks, S. A., Dillon, G. K., & Miller, C. (2014). A new metric for quantifying burn severity: The Relativized
      Burn Ratio. Remote Sensing, 6(3), 1827–1844. https://doi.org/10.3390/rs6031827
    Silva-Cardoza, A. I., Vega-Nieva, D. J., Briseño-Reyes, J., Briones-Herrera, C. I., López-Serrano, P. M.,
      Corral-Rivas, J. J., Parks, S. A., & Holsinger, L. M. (2022). Evaluating a new relative phenological
      correction and the effect of Sentinel-based Earth Engine compositing approaches to map fire severity and
      burned area. Remote Sensing, 14(13), 3122. https://doi.org/10.3390/rs14133122
    Veraverbeke, S., Lhermitte, S., Verstraeten, W. W., & Goossens, R. (2010). The temporal dimension of differenced
      Normalized Burn Ratio (dNBR) fire/burn severity studies: The case of the large 2007 Peloponnese wildfires in
      Greece. Remote Sensing of Environment, 114(11), 2548–2563. https://doi.org/10.1016/j.rse.2010.05.029
"""

import ee

# (class, lowest dNBR of the class, name, as in gee/core.js): a class goes from its lowest dNBR to that of the next one
SEVERITY = [
	(-2, None, 'Enhanced regrowth, high'),  # dNBR < -0.25
	(-1, -0.25, 'Enhanced regrowth, low'),
	(0, -0.1, 'Unburned'),
	(1, 0.1, 'Low severity'),
	(2, 0.27, 'Moderate-low severity'),
	(3, 0.44, 'Moderate-high severity'),
	(4, 0.66, 'High severity'),
]
BURNED = 0.1  # dNBR from which a pixel is burned (class 1 and above)
# colours of the classes of UN-SPIDER (Recommended Practice: Burn Severity Mapping in Google Earth Engine,
# https://un-spider.org/advisory-support/recommended-practices/recommended-practice-burn-severity/burn-severity-earth-engine),
# also in gee/core.js
COLOURS = {-2: '7a8737', -1: 'acbe4d', 0: '0ae042', 1: 'fff70b', 2: 'ffaf38', 3: 'ff641b', 4: 'a41fd6'}
# range of the colours of the maps of the RBR (the diverging ramp of the trends, reversed: burned in red), as in the
# Earth Engine app
RBR_RANGE = (-0.5, 0.5)

# The classes of the RdNBR of Miller & Thode 2007 (their Table 4, as in gee/core.js): the RdNBR predicted by their
# regression on the composite burn index (CBI) of 741 plots of 14 fires at the limits of the CBI classes of their
# Table 2 (unchanged 0-0.1, low 0.1-1.24, moderate 1.25-2.24, high 2.25-3), here without their factor 1000: unchanged
# < 69, low 69-315, moderate 316-640, high >= 641 there. 'Unchanged', not 'unburned': one year after the fire the area
# was indistinguishable from before it, which does not always mean that it did not burn (their Table 2).
RDNBR_SEVERITY = [
	(0, None, 'Unchanged'),  # RdNBR < 0.069
	(1, 0.069, 'Low severity'),
	(2, 0.316, 'Moderate severity'),
	(3, 0.641, 'High severity'),
]
RDNBR_BURNED = 0.069  # RdNBR from which a pixel changed (class 1, low, and above)
# The article draws its classes in grey; these are the colours of UN-SPIDER of the classes of the dNBR of the same
# name (unburned, low, moderate-high, high), so that both maps read alike
RDNBR_COLOURS = {0: '0ae042', 1: 'fff70b', 2: 'ff641b', 3: 'a41fd6'}
# range of the colours of the maps of the continuous RdNBR (the reversed diverging ramp, like the RBR): that of the
# figures of Miller & Thode 2007 is -500 to 1200 (x 1000)
RDNBR_RANGE = (-1.2, 1.2)

# The statistics of the RBR and the RdNBR over each region (stats_reducer; burnStatsReducer in gee/core.js): Earth
# Engine computes a percentile, and a median, from a histogram whose buckets, of a width that is a power of 2, span the
# values with at most so many buckets. With its default, a few outliers widened the buckets: the RdNBR -16 and 4 of
# the unburned surroundings of the fire of Sierra Bermeja (Sentinel-2, 2021 to 2022) made them 0.125 wide, and gave
# the same percentile 10 and median (-0.049; -0.120 and -0.037 in the pixels of its GeoTIFF). With 2 ** 16 buckets they
# are 0.0005 wide there (the percentiles within 0.0002 of those of the pixels), and at most 0.002 over the widest range
# of the RdNBR (-63 to 63, with |NBR before| at least 0.001).
PERCENTILE_BUCKETS = 2 ** 16

# The burn indices with classes: their classes, colours, the value from which a pixel is burned (or changed) and the
# name of the columns of the limits of their classes (dnbr_min and dnbr_max, rdnbr_min and rdnbr_max)
CLASSES = {
	'dNBR': {'classes': SEVERITY, 'colours': COLOURS, 'burned': BURNED, 'key': 'dnbr',
	         'scale': 'USGS, Key & Benson 2006'},
	'RdNBR': {'classes': RDNBR_SEVERITY, 'colours': RDNBR_COLOURS, 'burned': RDNBR_BURNED, 'key': 'rdnbr',
	          'scale': 'Miller & Thode 2007 (Table 4)'},
}


def _classes(index):
	"""The classes of INDEX ('dNBR' or 'RdNBR', any case)."""
	key = {k.lower(): k for k in CLASSES}.get(str(index or 'dNBR').lower())
	if key is None:
		raise ValueError(f"the burn index {index} has no classes: use {' or '.join(CLASSES)}")
	return CLASSES[key]


def limits(cls, index='dNBR'):
	"""(lowest, highest) value of INDEX of a class (None at the ends)."""
	classes = _classes(index)['classes']
	i = [c for c, _, _ in classes].index(cls)
	return classes[i][1], classes[i + 1][1] if i + 1 < len(classes) else None


def legend(index='dNBR'):
	"""The classes of INDEX ('dNBR', the default, or 'RdNBR') with their colours, for the legends of the maps (those of
	the assistant, its reports, the QGIS plugin and the viewer): [{'value', 'label', 'color' ('#rrggbb'), '<key>_min',
	'<key>_max'}] (key: dnbr or rdnbr), from the lowest class to high severity."""
	c = _classes(index)
	key = c['key']
	return [{'value': v, 'label': label, 'color': '#' + c['colours'][v], f'{key}_min': limits(v, index)[0],
	         f'{key}_max': limits(v, index)[1]} for v, _, label in c['classes']]


def class_label(c):
	"""The label of a class (one of legend()) in a legend, with the values of its index: «Low severity (dNBR 0.1 to
	0.27)», «High severity (RdNBR ≥ 0.641)»."""
	num = lambda v: '0' if v == 0 else f'{v:.4g}'  # noqa: E731
	key = 'rdnbr' if 'rdnbr_min' in c or 'rdnbr_max' in c else 'dnbr'
	low, high = c.get(f'{key}_min'), c.get(f'{key}_max')
	values = f'< {num(high)}' if low is None else f'≥ {num(low)}' if high is None else f'{num(low)} to {num(high)}'
	return f"{c['label']} ({'RdNBR' if key == 'rdnbr' else 'dNBR'} {values})"


def index_of(bands):
	"""The burn index of a GeoTIFF of burn_severity with the bands BANDS: 'RdNBR' (band rdnbr), 'RBR' (band rbr),
	'dNBR' (band severity without rdnbr) or None."""
	bands = list(bands or [])
	if 'rdnbr' in bands:
		return 'RdNBR'
	if 'rbr' in bands:
		return 'RBR'
	return 'dNBR' if 'severity' in bands else None


def map_style(bands):
	"""How the GeoTIFF of a burn severity with the bands BANDS is drawn, the same in every tool (the assistant and its
	reports, the QGIS plugin; the Earth Engine app and the viewer have these colours too): {'band' (its number),
	'classes' (legend() of its index, see index_of)} for the dNBR and the RdNBR, their band severity with the colours
	of their classes (those of the USGS, those of Miller & Thode 2007); {'band', 'min', 'max', 'palette'} for the RBR,
	its band rbr with the diverging ramp of the trends reversed (burned in red) from RBR_RANGE (and for an RdNBR
	without its band severity, its band rdnbr from RDNBR_RANGE); None without those bands."""
	bands = list(bands or [])
	index = index_of(bands)
	if index in CLASSES and 'severity' in bands:
		return {'band': bands.index('severity') + 1, 'classes': legend(index)}
	if index in ('RBR', 'RdNBR'):
		from .trends import DIVERGING
		band, (lo, hi) = ('rbr', RBR_RANGE) if index == 'RBR' else ('rdnbr', RDNBR_RANGE)
		return {'band': bands.index(band) + 1, 'min': lo, 'max': hi, 'palette': list(reversed(DIVERGING))}
	return None


def classify(value, index='dNBR'):
	"""ee.Image of the class of each pixel of the ee.Image VALUE of INDEX ('dNBR', the default, classes -2 to 4; or
	'RdNBR', classes 0 to 3), masked as it."""
	classes = _classes(index)['classes']
	cls = ee.Image.constant(classes[0][0])
	for _, low, _ in classes[1:]:
		cls = cls.add(value.gte(low))
	return cls.updateMask(value.mask()).toInt8().rename('severity')


def rbr(dnbr, nbr_before):
	"""ee.Image of the Relativized Burn Ratio (Parks et al. 2014), RBR = dNBR / (NBR before + 1.001), from the
	ee.Images DNBR and NBR_BEFORE, on the scale of the dNBR (without the factor 1000 of the articles)."""
	from .catalog import RBR_OFFSET
	return dnbr.divide(nbr_before.add(RBR_OFFSET)).rename('rbr')


def rdnbr(dnbr, nbr_before):
	"""ee.Image of the relative dNBR (Miller & Thode 2007), RdNBR = dNBR / sqrt(|NBR before|), with |NBR before| at
	least 0.001 (catalog.RDNBR_MIN_NBR, Howe et al. 2022), from the ee.Images DNBR and NBR_BEFORE, on the scale of the
	dNBR (the article multiplies the NBR by 1000: an RdNBR of 0.641 here is 641 there)."""
	from .catalog import RDNBR_MIN_NBR
	return dnbr.divide(nbr_before.abs().max(RDNBR_MIN_NBR).sqrt()).rename('rdnbr')


def stats_reducer():
	"""ee.Reducer of the statistics of the RBR or the RdNBR over a region: its mean, median ('median'), percentiles 10
	and 90 ('p10', 'p90'), minimum and maximum, the percentiles from a histogram of PERCENTILE_BUCKETS buckets, so that
	a few outliers do not make them coarse."""
	percentiles = ee.Reducer.percentile([10, 50, 90], ['p10', 'median', 'p90'], PERCENTILE_BUCKETS)
	return ee.Reducer.mean().combine(percentiles, '', True).combine(ee.Reducer.minMax(), '', True)


def table(groups, region, index='dNBR'):
	"""Rows [{region, class, label, <key>_min, <key>_max, ha}] (key: dnbr for the dNBR, rdnbr for the RdNBR) of every
	class of INDEX, from the GROUPS of an Earth Engine grouped sum of hectares ([{'class', 'sum'}])."""
	c = _classes(index)
	key = c['key']
	ha = {int(g['class']): g['sum'] for g in groups or []}
	rows = []
	for cls, _, label in c['classes']:
		low, high = limits(cls, index)
		rows.append({'region': region, 'class': cls, 'label': label, f'{key}_min': low, f'{key}_max': high,
		             'ha': ha.get(cls, 0.0)})
	return rows
