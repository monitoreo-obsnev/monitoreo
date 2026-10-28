"""MonitorEO for QGIS: time series, maps and exports of the variables of MonitorEO (OBSNEV) with Google Earth Engine."""


def classFactory(iface):
	from .plugin import MonitorEOPlugin
	return MonitorEOPlugin(iface)
