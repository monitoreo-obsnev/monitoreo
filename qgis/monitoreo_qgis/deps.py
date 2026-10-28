"""Libraries of the plugin: monitoreo and earthengine-api, with its pure Python dependencies, in ext/ (made by
build_plugin.py). They go to the end of sys.path, so the packages of QGIS come first and these only fill the gaps."""

import os
import sys
import warnings

EXT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ext')


def setup_path():
	if os.path.isdir(EXT) and EXT not in sys.path:
		sys.path.append(EXT)
		# the Google libraries warn that the Python of QGIS 3 (3.9) is old; they work with it
		warnings.filterwarnings('ignore', category=FutureWarning, module=r'google\.')


def missing():
	"""Why monitoreo or ee cannot be imported (None if they can)."""
	setup_path()
	try:
		import ee  # noqa: F401
		import monitoreo  # noqa: F401
	except ImportError as e:
		return str(e)
	return None
