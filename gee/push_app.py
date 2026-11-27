"""Publish the app of MonitorEO from the git repository of its scripts in Earth Engine.

The app is the script app of the repository users/monitoreo-obsnev/monitoreo (account everest@go.ugr.es, Earth Engine
user monitoreo-obsnev): ui.js, which requires the module core (core.js), which requires the modules of the catalog
catalog_1, catalog_2... (gee/build.py modules: Earth Engine refuses any file of a repository over 512 KiB). This script writes them into a clone of that
repository (~/.cache/monitoreo/gee-app), commits them if something changed, pushes the commit to the repository and
then to its backup, users/javiermartinez/monitoreo, a mirror whose master goes to the same commit:

  python gee/push_app.py              # after the merge, on main as GitHub has it (git switch main && git pull)
  python gee/push_app.py --dry-run    # write and commit in the clone, push nothing

The backup never loses a version: its master moves only forward (it is in the history of the new commit), or replaces
a backup without the app (a single commit, as the test README it was created with); otherwise nothing is pushed (a
repository of the app lost or recreated: restore it from the backup first), unless --replace-backup. Before pushing,
it reads the backup with its own cookie, so a cookie that does not work stops it before the repository of the app
moves. With another --repo (a test), --backup is required: the default backup mirrors only the repository of the app.

Then, in the Code Editor with the account of the project: Apps > the pencil of MonitorEO > Overwrite from repository
script path users/monitoreo-obsnev/monitoreo:app > UPDATE.

Git reads the credential of each repository from a cookie file of earthengine.googlesource.com (new-password there):
that of everest in ~/.gitcookies-everest and that of the backup in ~/.gitcookies. The script only passes their paths
to git; it never reads, prints nor logs a cookie. Nothing in this script computes in Earth Engine.
"""

import argparse
import hashlib
import importlib.util
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HOST = 'https://earthengine.googlesource.com/'
BACKUP = 'users/javiermartinez/monitoreo'  # the mirror of the repository of the app
COOKIES = '~/.gitcookies-everest'  # the cookie file of everest@go.ugr.es
BACKUP_COOKIES = '~/.gitcookies'  # the cookie file of the account of the backup
CACHE = '~/.cache/monitoreo/gee-app'  # the clone of the repository of the app
BRANCH = 'master'  # the branch of the repositories of Earth Engine
BACKUP_REF = 'refs/remotes/backup/master'  # the master of the backup, as the clone last read it
SOURCE = 'monitoreo-obsnev/monitoreo'  # the GitHub repository of the code


def _build():
	"""gee/build.py as a module (its functions: it computes nothing until its main runs)."""
	spec = importlib.util.spec_from_file_location('monitoreo_gee_build', os.path.join(HERE, 'build.py'))
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


build = _build()
REPO = build.REPO  # the repository of the app: users/monitoreo-obsnev/monitoreo


class PublishError(Exception):
	"""The app cannot be published: what to do is in the message."""


def run_git(args, cwd=None, cookies=None):
	"""Run git ARGS in CWD and return what it writes. COOKIES: the path of the cookie file of
	earthengine.googlesource.com for this call (only its path goes to git, as http.cookiefile). Git never asks for a
	password here: without a valid cookie it fails. PublishError if git fails."""
	cmd = ['git'] + (['-c', f'http.cookiefile={cookies}'] if cookies else []) + list(args)
	run = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=dict(os.environ, GIT_TERMINAL_PROMPT='0'))
	if run.returncode:
		raise PublishError(f"git {' '.join(args)} failed: {(run.stderr or run.stdout).strip()}")
	return run.stdout


def plugin_version(root=ROOT):
	"""The version of the QGIS plugin (version= of qgis/monitoreo_qgis/metadata.txt), that of the tag of the release."""
	with open(os.path.join(root, 'qgis', 'monitoreo_qgis', 'metadata.txt'), encoding='utf-8') as f:
		return re.search(r'^version=(\S+)', f.read(), re.M).group(1)


def check_checkout(git, root=ROOT, allow_any=False):
	"""The commit of the checkout ROOT of monitoreo, and whether gee/ has uncommitted changes. PublishError unless its
	HEAD is the main of GitHub as GitHub has it now (git ls-remote origin: a local origin/main may be from before the
	merge) and gee/ has no uncommitted change (the app is published after a merge), with ALLOW_ANY (which asks GitHub
	nothing)."""
	head = git(['rev-parse', 'HEAD'], cwd=root).strip()
	dirty = bool(git(['status', '--porcelain', '--', 'gee'], cwd=root).strip())
	if not allow_any:
		try:
			main = (git(['ls-remote', 'origin', 'refs/heads/main'], cwd=root).split() or [''])[0]
		except PublishError as error:
			raise PublishError(f'cannot ask GitHub for its main (git ls-remote origin), to check that the checkout is '
			                   f'at it: {error}; or --allow-any') from None
		if head != main:
			raise PublishError(f"the checkout is at {head[:7]}, not at main as GitHub has it ({main[:7] or 'none'}): "
			                   'the app is published after the merge, from main (git switch main && git pull), or '
			                   '--allow-any')
		if dirty:
			raise PublishError('gee/ has uncommitted changes (git status gee): the app is published from what main has, '
			                   'or --allow-any')
	return head, dirty


def cookie_file(path, repo):
	"""PATH with ~ expanded; PublishError if there is no such file (its content is never read)."""
	full = os.path.expanduser(path)
	if not os.path.isfile(full):
		how = ('' if full == os.path.expanduser('~/.gitcookies') else
		       f' with {path} in place of ~/.gitcookies (without its line git config --global)')
		raise PublishError(f'no cookie file {path} for the repository {repo}: open {HOST}new-password signed in with '
		                   f'the Google account of its owner and run the script it gives{how}')
	return full


def update_clone(git, url, cache, cookies):
	"""The clone CACHE (an absolute path) of the repository URL (cloned if missing) on its branch master as the
	repository has it, without anything else (an empty repository: master without commits)."""
	if not os.path.isdir(os.path.join(cache, '.git')):
		os.makedirs(os.path.dirname(cache), exist_ok=True)
		git(['clone', '--quiet', url, cache], cookies=cookies)
	else:
		git(['remote', 'set-url', 'origin', url], cwd=cache)
		git(['fetch', '--quiet', '--prune', 'origin'], cwd=cache, cookies=cookies)
	if git(['branch', '--remotes', '--list', f'origin/{BRANCH}'], cwd=cache).strip():
		git(['checkout', '--quiet', '--force', '-B', BRANCH, f'origin/{BRANCH}'], cwd=cache)
	else:  # an empty repository: its first commit
		git(['symbolic-ref', 'HEAD', f'refs/heads/{BRANCH}'], cwd=cache)
		git(['update-ref', '-d', f'refs/heads/{BRANCH}'], cwd=cache)
		git(['read-tree', '--empty'], cwd=cache)
	git(['clean', '-fdxq'], cwd=cache)


def read_backup(git, url, cache, cookies):
	"""The commit of the master of the backup URL (None if it has none), read with its cookie file COOKIES and fetched
	into the clone CACHE as BACKUP_REF. PublishError if git cannot read it (a cookie expired, or of an account that
	cannot read it): nothing is pushed then."""
	try:
		heads = git(['ls-remote', url, f'refs/heads/{BRANCH}'], cwd=cache, cookies=cookies).split()
		if heads:
			git(['fetch', '--quiet', url, f'+refs/heads/{BRANCH}:{BACKUP_REF}'], cwd=cache, cookies=cookies)
	except PublishError as error:
		raise PublishError(f'cannot read the backup {url} with the cookie file {cookies}, so nothing was pushed: renew '
		                   f'it at {HOST}new-password signed in with the account of the backup and run push_app.py '
		                   f'again ({error})') from None
	return heads[0] if heads else None


def mirror_mode(git, cache, backup_commit, commit, replace=False):
	"""How the master of the backup (at BACKUP_COMMIT, None if it has none) goes to COMMIT without losing a version:
	'new' (it had no master), 'up to date', 'fast-forward' (BACKUP_COMMIT is in the history of COMMIT) or 'replaced
	its test commit' (a single commit without any file of the app, as the test README the backup was created with);
	with REPLACE, 'replaced' whatever it had. None otherwise: its history would be lost."""
	if backup_commit is None:
		return 'new'
	if backup_commit == commit:
		return 'up to date'
	if git(['rev-list', '--count', f'{commit}..{backup_commit}'], cwd=cache).strip() == '0':
		return 'fast-forward'
	if git(['rev-list', '--count', backup_commit], cwd=cache).strip() == '1':
		names = git(['ls-tree', '--name-only', backup_commit], cwd=cache).split()
		if not any(build.MODULE.fullmatch(n) for n in names):
			return 'replaced its test commit'
	return 'replaced' if replace else None


def publish(repo=REPO, backup=None, cookies=COOKIES, backup_cookies=BACKUP_COOKIES, cache=CACHE, dry_run=False,
            allow_any=False, git=None, root=ROOT, files=None, replace_backup=False):
	"""Write the files of the app (FILES, {name: text}; by default gee/build.py modules(REPO)) into the clone CACHE of
	the repository REPO of Earth Engine, commit them if something changed, push the commit to REPO (with the cookie
	file COOKIES) and then to the master of BACKUP (with BACKUP_COOKIES; BACKUP by default, but only for REPO: another
	repository needs its own BACKUP). With DRY_RUN, push nothing. The backup is read before the first push, and its
	master only moves forward (mirror_mode): PublishError, with nothing pushed, if it would lose a version (unless
	REPLACE_BACKUP), or if it cannot be read. GIT runs git (run_git: tests give another). PublishError unless the
	checkout ROOT of monitoreo is the main of GitHub without changes in gee/ (or ALLOW_ANY). What was done: {'commit',
	'message', 'changed', 'removed', 'pushed', 'mirror', 'clone', 'repo', 'backup', 'path', 'files': {name: (bytes,
	SHA-256)}}."""
	git = git or run_git
	if backup is None:
		if repo == REPO:
			backup = BACKUP
		elif not dry_run:
			raise PublishError(f'no backup for {repo}: give it with --backup (the default backup, {BACKUP}, only '
			                   f'mirrors {REPO})')
	if backup == repo:
		raise PublishError(f'the backup of {repo} cannot be the repository itself')
	head, dirty = check_checkout(git, root, allow_any)
	cookies = cookie_file(cookies, repo)
	if not dry_run:
		backup_cookies = cookie_file(backup_cookies, backup)
	if files is None:
		files = build.modules(repo)  # before the network: a file too big stops here
	message = (f'MonitorEO app v{plugin_version(root)} (gee of {SOURCE} {head[:7]}'
	           f"{' with uncommitted changes' if dirty else ''})")
	cache = os.path.abspath(os.path.expanduser(cache))  # a relative path, from the current folder
	update_clone(git, HOST + repo, cache, cookies)
	removed = build.write_modules(cache, files)
	git(['add', '--all', '.'], cwd=cache)
	changed = bool(git(['status', '--porcelain'], cwd=cache).strip())
	if changed:
		git(['commit', '--quiet', '-m', message], cwd=cache)
	commit = git(['rev-parse', 'HEAD'], cwd=cache).strip()
	message = git(['log', '-1', '--format=%s'], cwd=cache).strip()  # that of the commit pushed
	mode = None
	if not dry_run:
		backup_commit = read_backup(git, HOST + backup, cache, backup_cookies)
		mode = mirror_mode(git, cache, backup_commit, commit, replace_backup)
		if mode is None:
			raise PublishError(
				f'the master of the backup {HOST + backup} ({backup_commit[:7]}) is not in the history of the new commit '
				f'{commit[:7]} of {HOST + repo}: mirroring it would lose versions of the backup, so nothing was pushed. '
				f'If the repository of the app was lost or recreated, restore it from its backup first (in {cache}: '
				f'git -c http.cookiefile={cookies} push {HOST + repo} {BACKUP_REF}:refs/heads/{BRANCH}) and run '
				f'push_app.py again; --replace-backup replaces the history of the backup with that of the app')
		git(['push', '--quiet', 'origin', f'HEAD:refs/heads/{BRANCH}'], cwd=cache, cookies=cookies)
		lease = ([f'--force-with-lease=refs/heads/{BRANCH}:{backup_commit}'] if mode.startswith('replaced') else [])
		try:
			git(['push', '--quiet'] + lease + [HOST + backup, f'{commit}:refs/heads/{BRANCH}'], cwd=cache,
			    cookies=backup_cookies)
		except PublishError as error:
			raise PublishError(
				f'the repository of the app {HOST + repo} is already at {commit[:7]} ({BRANCH}), but its backup '
				f'{HOST + backup} was not mirrored: {error}. Check or renew the cookie file of the backup '
				f'({backup_cookies}) at {HOST}new-password, signed in with the account of the backup, and run '
				'push_app.py again: it commits nothing new and mirrors the backup. Then, in the Code Editor: Apps > the '
				f'pencil of MonitorEO > Overwrite from repository script path {repo}:app > UPDATE') from None
	return {'commit': commit, 'message': message, 'changed': changed, 'removed': removed, 'pushed': not dry_run,
	        'mirror': mode, 'clone': cache, 'repo': HOST + repo, 'backup': backup and HOST + backup, 'path': f'{repo}:app',
	        'files': {name: (len(text.encode('ascii')), hashlib.sha256(text.encode('ascii')).hexdigest())
	                  for name, text in files.items()}}


def report(done):
	"""The lines that say what publish DONE."""
	lines = [f"{'committed' if done['changed'] else 'nothing changed: the last commit,'} {done['commit'][:7]} "
	         f"{done['message']!r}, in {done['clone']}"]
	if done['removed']:
		lines.append(f"removed {', '.join(done['removed'])}")
	if done['pushed']:
		lines += [f"pushed to {done['repo']} ({BRANCH})", f"mirrored to {done['backup']} ({BRANCH}, {done['mirror']})",
		          f"In the Code Editor: Apps > the pencil of MonitorEO > Overwrite from repository script path "
		          f"{done['path']} > UPDATE"]
	else:
		lines.append(f"dry run: nothing pushed (the app would be {done['path']})")
	lines.append('files (bytes, SHA-256):')
	lines += [f'  {name:<10} {size:>7} {digest}' for name, (size, digest) in done['files'].items()]
	return lines


def main(argv=None):
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument('--repo', default=REPO, help=f'the repository of the app (default: {REPO})')
	parser.add_argument('--backup', help=f'its backup, a mirror (default: {BACKUP} with the default --repo; required '
	                                     'with another --repo, unless --dry-run)')
	parser.add_argument('--cookies', default=COOKIES,
	                    help=f'the cookie file of the account of the repository (default: {COOKIES})')
	parser.add_argument('--backup-cookies', default=BACKUP_COOKIES,
	                    help=f'the cookie file of the account of the backup (default: {BACKUP_COOKIES})')
	parser.add_argument('--cache', default=CACHE, help=f'the clone of the repository (default: {CACHE})')
	parser.add_argument('--dry-run', action='store_true', help='write and commit in the clone, push nothing')
	parser.add_argument('--allow-any', action='store_true',
	                    help='publish also when the checkout is not the main of GitHub or gee/ has uncommitted changes')
	parser.add_argument('--replace-backup', action='store_true',
	                    help='replace the history of the backup with that of the repository when its master is not in '
	                         'it (its versions not in the repository are lost; otherwise nothing is pushed)')
	args = parser.parse_args(argv)
	try:
		done = publish(args.repo, args.backup, args.cookies, args.backup_cookies, args.cache, args.dry_run,
		               args.allow_any, replace_backup=args.replace_backup)
	except (PublishError, ValueError, OSError) as error:
		sys.exit(f'push_app: {error}')
	print('\n'.join(report(done)))


if __name__ == '__main__':
	main()
