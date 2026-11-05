"""Burn severity of a fire from the NBR (Normalized Burn Ratio, catalog entries 101 Landsat and 102 Sentinel-2):
dNBR = NBR before - NBR after the fire, classified with the scale of the USGS (Key & Benson 2006, Landscape
Assessment, FIREMON; https://www.fs.usda.gov/rm/pubs_series/rmrs/gtr/rmrs_gtr164/rmrs_gtr164_13_land_assess.pdf).
Or the RBR (Relativized Burn Ratio, Parks et al. 2014; catalog entries 103 Sentinel-2 and 104 Landsat, as computed by
Silva-Cardoza et al. 2022, https://doi.org/10.3390/rs14133122): dNBR / (NBR before + 1.001), a continuous index.

The NBR before and after are the METRIC (the median by default) of the images of a period before and of a period
after the fire, with the pixel filters of MonitorEO (clouds, shadows, water, snow).
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


def limits(cls):
	"""(lowest, highest) dNBR of a class (None at the ends)."""
	i = [c for c, _, _ in SEVERITY].index(cls)
	return SEVERITY[i][1], SEVERITY[i + 1][1] if i + 1 < len(SEVERITY) else None


def classify(dnbr):
	"""ee.Image of the class (-2 to 4) of each pixel of the ee.Image DNBR, masked as it."""
	cls = ee.Image.constant(SEVERITY[0][0])
	for _, low, _ in SEVERITY[1:]:
		cls = cls.add(dnbr.gte(low))
	return cls.updateMask(dnbr.mask()).toInt8().rename('severity')


def rbr(dnbr, nbr_before):
	"""ee.Image of the Relativized Burn Ratio (Parks et al. 2014), RBR = dNBR / (NBR before + 1.001), from the
	ee.Images DNBR and NBR_BEFORE, on the scale of the dNBR (without the factor 1000 of the articles)."""
	from .catalog import RBR_OFFSET
	return dnbr.divide(nbr_before.add(RBR_OFFSET)).rename('rbr')


def table(groups, region):
	"""Rows [{region, class, label, dnbr_min, dnbr_max, ha}] of every class, from the GROUPS of an Earth Engine
	grouped sum of hectares ([{'class', 'sum'}])."""
	ha = {int(g['class']): g['sum'] for g in groups or []}
	rows = []
	for cls, _, label in SEVERITY:
		low, high = limits(cls)
		rows.append({'region': region, 'class': cls, 'label': label, 'dnbr_min': low, 'dnbr_max': high,
		             'ha': ha.get(cls, 0.0)})
	return rows
