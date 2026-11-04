"""The maps of each step of a result: its years, months or periods of 16 days, or the parts of the year of a trend.
The assistant offers them in its page and the QGIS plugin in the windows of its results."""

import datetime as dt

from . import composite
from .publish import MONTHS, period_text

PERIOD_MAP = ('time_series', 'region_stats', 'compare_series', 'trend_table')  # with the map of their period
MAX_MAP_STEPS = 400  # maps of the steps of a result that are offered (the last ones)
UNITS = {'annual': 'años', 'monthly': 'meses', '16-day': 'periodos de 16 días'}


def map_steps(tool, args):
	"""[{'key', 'label', 'start', 'end'}] of the maps of each step of a result: its years, months or periods of 16
	days (its step, or the temporal aggregation of its map; years for a whole period), with its season. [] if it is
	not a map of a variable nor a result over regions, or if it has only one step. Those of a trend are its parts of
	the year (the trend of each month or 16 days, key 'part:N')."""
	if tool in ('trend_table', 'trend_map'):
		n = {'monthly': 12, '16-day': 23}.get(args.get('step'), 0)
		return [{'key': f'part:{p}', 'label': f'Tendencia de {MONTHS[p - 1]}' if n == 12 else
		         f'Tendencia del periodo {p} de 16 días', 'part': p} for p in range(1, n + 1)]
	if tool not in PERIOD_MAP + ('map_layer',) or not args.get('start') or not args.get('end'):
		return []
	unit = args.get('temporal') if tool in ('map_layer', 'region_stats') else args.get('step')
	unit = 'monthly' if unit == 'daily' else unit if unit in UNITS else 'annual'
	try:
		wins = composite.windows((args['start'][:10], args['end'][:10]), args.get('season'))
	except (ValueError, TypeError):
		return []
	parts = [(ws, we) for _, ws, we in wins] if unit == 'annual' else \
	        [(bs, be) for win in wins for _, bs, be in composite.bins(win, unit)]
	steps = []
	for first, after in parts[-MAX_MAP_STEPS:]:
		last = after - dt.timedelta(days=1)
		label = str(first.year) if unit == 'annual' and first.year == last.year else \
		        f'{MONTHS[first.month - 1][:3]} {first.year}' if unit == 'monthly' else \
		        period_text(first.isoformat(), last.isoformat())
		steps.append({'key': f'{first.isoformat()}/{last.isoformat()}', 'label': label, 'start': first.isoformat(),
		              'end': last.isoformat()})
	return steps if len(steps) > 1 else []
