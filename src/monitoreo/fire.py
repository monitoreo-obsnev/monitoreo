"""Burn severity of a fire from the NBR (Normalized Burn Ratio, catalog entries 101 Landsat and 102 Sentinel-2):
dNBR = NBR before - NBR after the fire, classified with the scale of the USGS (Key & Benson 2006, Landscape
Assessment, FIREMON; https://www.fs.usda.gov/rm/pubs_series/rmrs/gtr/rmrs_gtr164/rmrs_gtr164_13_land_assess.pdf).

The NBR before and after are the METRIC (the median by default) of the images of a period before and of a period
after the fire, with the pixel filters of MonitorEO (clouds, shadows, water, snow).
"""

import ee

# (class, lowest dNBR of the class, name): a class goes from its lowest dNBR to that of the next one
SEVERITY = [
	(-2, None, 'Rebrote alto'),  # enhanced regrowth, high: dNBR < -0.25
	(-1, -0.25, 'Rebrote bajo'),  # enhanced regrowth, low
	(0, -0.1, 'No quemado'),  # unburned
	(1, 0.1, 'Severidad baja'),  # low severity
	(2, 0.27, 'Severidad moderada-baja'),  # moderate-low severity
	(3, 0.44, 'Severidad moderada-alta'),  # moderate-high severity
	(4, 0.66, 'Severidad alta'),  # high severity
]
BURNED = 0.1  # dNBR from which a pixel is burned (class 1 and above)
COLOURS = {-2: '1a9850', -1: '91cf60', 0: 'f2efe6', 1: 'fee08b', 2: 'fdae61', 3: 'f46d43', 4: '7a0177'}


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
