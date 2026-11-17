"""The parameters of an analysis of MonitorEO as JSON (issue #85), the same in every tool (the Python and R packages,
the command line, the MCP server, the assistant, the QGIS plugin and the Earth Engine app), to repeat an analysis,
change one of its parameters, or take it from one tool to another:

    {"monitoreo": "0.3.52", "analysis": "time_series",
     "parameters": {"region": {"wdpa_id": 555588816}, "variable": "NDVI", "sensor": "Landsat", "start": "2023-01-01",
                    "end": "2026-10-30", "step": "monthly", "metric": "mean", "stat": "mean"}}

ANALYSIS is the function of monitoreo.services, and PARAMETERS its arguments, with their names (those of the Python
and R packages, the command line and the MCP server), without its outputs (the files: each tool chooses its own).
Every result that writes files writes its parameters next to them (<file>.parameters.json, see monitoreo.readme), and
the tools save them and apply them: those that cannot be applied (not parameters of the analysis in this version, a
variable or a sensor that is not in the catalog) are left out and listed, with the reason (check)."""

import inspect
import json
import os

from . import __version__, catalog, publish

# the analyses: the functions of monitoreo.services that compute (their results are documented, see services._cited)
ANALYSES = ('time_series', 'time_series_to_drive', 'map_layer', 'map_figure', 'rgb_map', 'timelapse', 'region_stats',
            'transect', 'area_by_class', 'export_image', 'download_image', 'download_rgb', 'trend_table', 'trend_map',
            'download_trend', 'compare_series', 'compare_map', 'download_comparison', 'burn_severity')
SUFFIX = '.parameters.json'  # next to the files of a result: <file without extension>.parameters.json
META = ('monitoreo', 'analysis', 'parameters')


def _outputs():
	from . import readme  # outputs and callbacks: not parameters of what was computed
	return set(readme.NOT_ARGS)


def path_of(path):
	"""The file of the parameters of the file PATH of a result: <file without extension>.parameters.json."""
	return os.path.splitext(path)[0] + SUFFIX


def make(analysis, args):
	"""The parameters (see the module) of a call of ANALYSIS with ARGS: without its outputs nor the arguments left
	empty. The tools map_layer with figure and timelapse with video (MCP server, assistant) are their functions of
	monitoreo.services (map_figure, timelapse)."""
	from . import readme
	analysis, args = publish.services_call(analysis, dict(args or {}))
	if analysis not in ANALYSES:
		raise ValueError(f"{analysis} is not an analysis of MonitorEO: use one of {', '.join(ANALYSES)}")
	given = readme.call_args(args)
	given.update(given.pop('source', None) or {})  # the data of Earth Engine by their ID (collection, band...)
	_canonical(analysis, given)
	return {'monitoreo': __version__, 'analysis': analysis,
	        'parameters': json.loads(json.dumps(given, ensure_ascii=False, default=str))}


def _canonical(analysis, params):
	"""PARAMS (of ANALYSIS) in the one form that every tool takes: where as a list of conditions (a land cover mask
	alone is a dictionary in the services) and the perimeter of burn_severity as the name of its file (the MCP server
	and the assistant ask for it with true, and write it next to the GeoTIFF; false: none)."""
	if isinstance(params.get('where'), dict):
		params['where'] = [params['where']]
	if analysis == 'burn_severity' and isinstance(params.get('perimeter'), bool):
		if params['perimeter']:
			params['perimeter'] = 'perimeter.gpkg'
		else:
			del params['perimeter']
	return params


def save(analysis, args, path):
	"""Write the parameters of a call of ANALYSIS with ARGS (see make) to the JSON file PATH. Returns PATH."""
	path = os.path.expanduser(path)
	with open(path, 'w', encoding='utf-8') as f:
		json.dump(make(analysis, args), f, ensure_ascii=False, indent=2)
		f.write('\n')
	return path


def read(source):
	"""The parameters of SOURCE: a dictionary, a JSON text or the path of a JSON file (see the module), as
	{'monitoreo', 'analysis', 'parameters'}. A flat object ({"analysis": ..., "variable": ...}, as the issue proposed
	it) is taken too: every key but monitoreo and analysis is a parameter."""
	if isinstance(source, (str, os.PathLike)):
		text = str(source)
		if not text.lstrip().startswith('{'):
			text = os.path.expanduser(text)
			if not os.path.exists(text):
				raise ValueError(f'{text}: neither a JSON object of parameters nor the path of a file')
			with open(text, encoding='utf-8') as f:
				text = f.read()
		try:
			source = json.loads(text)
		except json.JSONDecodeError as e:
			raise ValueError(f'the parameters are not valid JSON: {e}') from None
	if not isinstance(source, dict):
		raise ValueError('the parameters are a JSON object: {"monitoreo": ..., "analysis": ..., "parameters": {...}}')
	params = source.get('parameters')
	if not isinstance(params, dict):
		params = {k: v for k, v in source.items() if k not in META}
	return {'monitoreo': source.get('monitoreo'), 'analysis': source.get('analysis'), 'parameters': dict(params)}


def accepted(analysis):
	"""The names of the parameters of ANALYSIS: those of its function of monitoreo.services and, if it takes the data
	of Earth Engine by their ID (**source), those of services.make_spec."""
	from . import services
	params = inspect.signature(getattr(services, analysis)).parameters
	names = {n for n, p in params.items() if p.kind not in (p.VAR_KEYWORD, p.VAR_POSITIONAL)}
	if any(p.kind == p.VAR_KEYWORD for p in params.values()):
		names |= {n for n in inspect.signature(services.make_spec).parameters if n != 'two_periods'}
	return names - _outputs()


def check(source):
	"""What of the parameters SOURCE (see read) can be applied in this version of MonitorEO: {'analysis',
	'parameters' (those that can), 'not_applied' ([{'name', 'value', 'reason'}]: not parameters of the analysis, its
	outputs, or a variable or a sensor that is not in the catalog), 'monitoreo' (the version that saved them) and
	'note' (when that version is not this one)}. An analysis that does not exist is an error (ValueError)."""
	p = read(source)
	analysis = p['analysis']
	if analysis not in ANALYSES:
		raise ValueError(f"unknown analysis {analysis!r}: the parameters say which one in \"analysis\", one of "
		                 f"{', '.join(ANALYSES)}")
	names, outputs = accepted(analysis), _outputs()
	ok, skipped = {}, []
	_canonical(analysis, p['parameters'])
	for name, value in p['parameters'].items():
		if name in names:
			ok[name] = value
		else:
			skipped.append({'name': name, 'value': value, 'reason': 'an output: each tool writes its own files'
			                if name in outputs else f'not a parameter of {analysis} in MonitorEO {__version__}'})
	variable = ok.get('variable')
	if variable and not ok.get('image'):  # a variable of the catalog (with its collection, or its ref, if given)
		try:
			catalog.find(variable, ok.get('sensor'), ok.get('collection'), ok.get('ref'))
		except KeyError as e:
			reason = str(e).strip('"\'')
			if ok.get('ref') is not None:  # an unknown ref: the variable and sensor may still be
				skipped.append({'name': 'ref', 'value': ok.pop('ref'), 'reason': reason})
				try:
					catalog.find(variable, ok.get('sensor'), ok.get('collection'))
					reason = None
				except KeyError as e2:
					reason = str(e2).strip('"\'')
			for name in ('variable', 'sensor', 'collection') if reason else ():
				if name in ok:
					skipped.append({'name': name, 'value': ok.pop(name), 'reason': reason})
	out = {'analysis': analysis, 'parameters': ok, 'not_applied': skipped, 'monitoreo': p['monitoreo']}
	if p['monitoreo'] and p['monitoreo'] != __version__:
		out['note'] = (f"saved with MonitorEO {p['monitoreo']}, applied in {__version__}: the parameters that changed "
		               'between them are in not_applied')
	return out


def run(source, **outputs):
	"""Compute the analysis of the parameters SOURCE (see read and check) with monitoreo.services, with OUTPUTS (its
	files: csv, chart, path...). Returns its result with 'not_applied' (and 'note') of check."""
	from . import services
	c = check(source)
	out = getattr(services, c['analysis'])(**c['parameters'], **outputs)
	if isinstance(out, dict):
		out['not_applied'] = c['not_applied']
		if c.get('note'):
			out['note'] = c['note']
	return out


def text(not_applied):
	"""The parameters that were not applied (see check), in a line: 'sensor (MODIS): reason; ...'."""
	return '; '.join(f"{p['name']} ({json.dumps(p['value'], ensure_ascii=False, default=str)}): {p['reason']}"
	                 for p in not_applied or [])
