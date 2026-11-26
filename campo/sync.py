"""MonitorEO Campo (campo/) and its own repository: bring its changes into monitoreo, send back those made here, and
give the app the core of this monitoreo.

campo/ is a git subtree of the repository of the app (kampax/monitoreo-campo), where it is developed and tried. Run it
from the root of monitoreo, on a branch of the change (never on main), with no changes pending:

    python campo/sync.py pull [SOURCE]   the commits of the app (SOURCE: its folder or URL, by default the folder
                                         in $MONITOREO_CAMPO or ../MCP monitoreo/monitoreo-campo, else its GitHub
                                         repository), merged into campo/, then the core of gee/ copied into it
    python campo/sync.py push [SOURCE]   the commits of campo/ made in monitoreo, sent to a branch monitoreo-<branch>
                                         of the repository of the app (merge it there)
    python campo/sync.py core            gee/core.js and gee/catalog.js copied into the page of the app
    python campo/sync.py check           whether the page of the app has the core of gee/ (exit 1 if not)

After pull or core, commit campo/ in the branch, test, and open the pull request as for any change of monitoreo.
"""

import argparse
import filecmp
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIX = 'campo'
LIB = os.path.join(ROOT, PREFIX, 'app', 'src', 'main', 'assets', 'www', 'lib')
GEE = os.path.join(ROOT, 'gee')
CORE = ('catalog.js', 'core.js')
REPOSITORY = 'https://github.com/kampax/monitoreo-campo.git'
BRANCH = 'main'


def default_source():
	"""The folder of the repository of the app on this computer, or its GitHub repository."""
	for d in (os.environ.get('MONITOREO_CAMPO'), os.path.join(ROOT, '..', 'MCP monitoreo', 'monitoreo-campo'),
	          os.path.join(ROOT, '..', 'monitoreo-campo')):
		if d and os.path.isdir(os.path.join(d, '.git')):
			return os.path.normpath(d)
	return REPOSITORY


def git(*args, capture=False):
	out = subprocess.run(['git', *args], cwd=ROOT, check=True, text=True,
	                     stdout=subprocess.PIPE if capture else None)
	return out.stdout.strip() if capture else None


def ready():
	"""The branch of the change, without changes pending (git subtree needs a clean tree)."""
	branch = git('rev-parse', '--abbrev-ref', 'HEAD', capture=True)
	if branch in ('main', 'master', 'HEAD'):
		sys.exit('campo/sync.py: switch to a branch of the change first (git switch -c <topic> origin/main), not '
		         + branch)
	if git('status', '--porcelain', '--untracked-files=no', capture=True):  # untracked files do not matter
		sys.exit('campo/sync.py: commit or stash the changes pending first')
	return branch


def stale():
	"""The files of the core that the page of the app has not got as gee/ has them."""
	return [n for n in CORE if not os.path.isfile(os.path.join(LIB, n))
	        or not filecmp.cmp(os.path.join(GEE, n), os.path.join(LIB, n), shallow=False)]


def core():
	old = stale()
	for n in CORE:
		shutil.copy(os.path.join(GEE, n), LIB)
	print('campo: the core of gee/ (' + ', '.join(CORE) + ')' + (' copied: ' + ', '.join(old) if old else
	                                                              ' was already there'))
	return old


def main(argv=None):
	p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
	p.add_argument('action', choices=['pull', 'push', 'core', 'check'])
	p.add_argument('source', nargs='?', help='folder or URL of the repository of the app')
	p.add_argument('--branch', default=BRANCH, help='its branch to pull (default main)')
	a = p.parse_args(argv)
	if a.action == 'check':
		old = stale()
		if old:
			sys.exit('campo: the page of the app has not got the core of gee/ (' + ', '.join(old) +
			         '): run python campo/sync.py core')
		print('campo: the page of the app has the core of gee/')
		return
	if a.action == 'core':
		core()
		return
	branch = ready()
	source = a.source or default_source()
	if a.action == 'pull':
		git('subtree', 'pull', '--prefix=' + PREFIX, '--squash', source, a.branch,
		    '-m', 'MonitorEO Campo: the changes of its repository (' + a.branch + ')')
		if core():
			print('campo: commit the core: git add campo && git commit -m "MonitorEO Campo with the core of gee/"')
		print('campo: pulled from ' + source + '. Test it, then open the pull request of ' + branch + '.')
	else:
		target = 'monitoreo-' + branch
		git('subtree', 'push', '--prefix=' + PREFIX, source, target)
		print('campo: pushed to the branch ' + target + ' of ' + source + '; merge it there into ' + a.branch + '.')


if __name__ == '__main__':
	main()
