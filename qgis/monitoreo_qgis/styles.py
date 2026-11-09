"""How the plugin colours the GeoTIFFs of its analyses, as the other tools of MonitorEO do (the Earth Engine app, the
assistant and its reports, the viewer of results): the classes and colours of the burn severity (monitoreo.fire) and
the ramp of the RBR. Pure Python, without QGIS, so that the tests check them without it; dock.py makes the renderers of
QGIS with them."""

from . import deps

deps.setup_path()
from monitoreo import fire, trends  # noqa: E402


def class_label(c):
	"""The label of a class of the burn severity (one of fire.legend()) with its dNBR, for the legend of its layer:
	«Low severity (dNBR 0.1 to 0.27)», as in the reports of the assistant."""
	low, high = c.get('dnbr_min'), c.get('dnbr_max')
	dnbr = f'< {high:g}' if low is None else f'≥ {low:g}' if high is None else f'{low:g} to {high:g}'
	return f"{c['label']} (dNBR {dnbr})"


def burn_style(res):
	"""How the GeoTIFF of the burn severity RES is coloured: {'band': its number, 'classes': [{'value', 'color'
	('#rrggbb'), 'label'}]} for the dNBR (its band severity, with the classes and colours of the USGS of
	fire.legend()); {'band', 'min', 'max', 'palette'} for the RBR (its band rbr, with the diverging ramp of the trends
	reversed, burned in red, from fire.RBR_RANGE); None without them."""
	bands = list(res.get('bands') or [])
	if 'severity' in bands:
		return {'band': bands.index('severity') + 1,
		        'classes': [dict(c, label=class_label(c)) for c in fire.legend()]}
	if 'rbr' in bands:
		return {'band': bands.index('rbr') + 1, 'min': fire.RBR_RANGE[0], 'max': fire.RBR_RANGE[1],
		        'palette': list(reversed(trends.DIVERGING))}
	return None
