# A release

After every merged PR that changes what users get (anything under `src/`, `qgis/`, `r/` or `gee/`, or the catalog):
team decision of 2026-11-09, so make it right after the merge without asking again, and tell the developer. A PR
that only changes the docs, the tests, the workflows or the skill waits for the next release; a stack of PRs merged
together gets one release after the last. The developer can also ask for one at any time: their request approves
all its steps, unless they say otherwise (e.g. "don't publish anything yet").

## Versions

There are two version numbers:

- **The package** `monitoreo` (Python and R): `pyproject.toml`, `src/monitoreo/__init__.py` (`__version__`) and
  `r/monitoreo/DESCRIPTION` (`Version:`), always the same.
- **The QGIS plugin**: `qgis/monitoreo_qgis/metadata.txt` (`version=`).

And one date: **the date of the release**, `__released__` in `src/monitoreo/__init__.py`, the same as in the heading of
the release in the changelog. The assistant, the QGIS plugin, the Earth Engine app and `monitoreo --version` show it
next to their version (the plugin and the app take it from the package they carry). `tests/test_changelog.py` and
`.github/changelog.py check` fail if it is not the date of the heading, and `tests/test_release_date.py` if the copy
of the Earth Engine app (`gee/catalog.js`, `gee/monitoreo_app.js`) has not got them.

The **tag** of a release is the plugin's version (`v0.3.15`). The workflow `qgis-plugin.yml` fails if they differ.
Raise both by one patch step unless the developer says otherwise. The last releases are in `git tag --sort=-v:refname`.

## Steps

1. A branch `release-<plugin version>` from an up-to-date `origin/main`.
2. One commit that raises the four files, sets `__released__` to the date of today, writes them into the copy of the
   Earth Engine app with `python gee/build.py --about-only` (without Earth Engine: `gee/catalog.js` and
   `gee/monitoreo_app.js`), and gives the release its entries in the changelog of `README.md`: rename
   `### Unreleased` to the heading of the release,
   `### [v<plugin version>](https://github.com/monitoreo-obsnev/monitoreo/releases/tag/v<plugin version>) · <date of
   today> · package <package version>`. Check the entries against what was merged since the last tag
   (`git log --oneline <last tag>..origin/main`): write those that a merged PR left out, in English and in the format
   of the others, and merge repeated ones. A release that users barely notice still gets one honest entry. Subject:
   `monitoreo <package version> and QGIS plugin <plugin version>: <what users get, in a few words>`.
3. Check what the workflows will check:
   - the offline tests (`tests/test_changelog.py` fails if the changelog has no release of the new versions);
   - `python .github/changelog.py notes v<plugin version>`: the notes that the GitHub release will have;
   - `python qgis/build_plugin.py`, which needs internet; with `bandit` and `detect-secrets` installed it runs the same
     security scan as plugins.qgis.org;
   - `metadata.txt` must have no `%` (plugins.qgis.org cannot read it).
4. Open the PR of the release, like any other change, and merge it when GitHub can merge it (the release is
   approved already).
5. After the merge, push an annotated tag on the merge commit,
   `git tag -a v<plugin version> -m "MonitorEO <plugin version>"` and `git push origin v<plugin version>`. The workflows
   then create the GitHub release (`qgis-plugin.yml` writes its notes from the changelog, attaches the plugin zip,
   whose `metadata.txt` has the changelog of the last releases for the plugin manager of QGIS, and uploads it to
   plugins.qgis.org;
   `installers.yml` attaches the assistant installers), and Zenodo archives the release with the metadata of
   `.zenodo.json`.
6. Check the release on GitHub. Uploads to plugins.qgis.org wait for a volunteer's approval.
7. Publish the Earth Engine app, after asking (it leaves this computer): on `main` after the merge
   (`git switch main && git pull`), `python gee/push_app.py`. It writes the app (`app` and the modules of the
   catalog `catalog_1`, `catalog_2`..., each under the 512 KiB per file that Earth Engine takes) into its clone of the
   repository of the app in Earth Engine, `users/monitoreo-obsnev/monitoreo` (account everest@go.ugr.es, cookie in
   `~/.gitcookies-everest`), commits them if something changed, pushes the commit there and then to its backup
   `users/javiermartinez/monitoreo` (always: a mirror; cookie in `~/.gitcookies`), and prints the path of the app and
   the SHA-256 of each file. It refuses a checkout that is not the `main` GitHub has now (it asks GitHub with
   `git ls-remote`: a local `origin/main` may be from before the merge) or with changes in `gee/`; `--dry-run` pushes
   nothing. The backup never loses a version: the script reads it with its own cookie before pushing anything, and its
   `master` only moves forward (or replaces the test README it was created with); otherwise nothing is pushed and the
   message says how to restore the repository of the app from the backup (`--replace-backup` only if the developer
   says the history of the backup may go). If the push to the backup fails after the one to the repository of the app,
   the message says so: renew the cookie and run it again, which mirrors it. Another `--repo` (a test) needs its own
   `--backup`. Then, in the Code Editor with the account of the project: **Apps** > the pencil of **MonitorEO** >
   **Overwrite from repository script path** `users/monitoreo-obsnev/monitoreo:app` > **UPDATE**. The fallback is to
   paste `gee/monitoreo_app.js` (wiki page Earth-Engine-app, "For administrators").

## Who gets what, and when

`### Unreleased` in the changelog is what is in `main` but not yet in the QGIS plugin nor in the Earth Engine app.
**Rule (2026-11-19):** it goes away only with a release of both: step 2 renames it to the heading of the release, and
step 7 publishes the app of that same release (after asking; if the developer says not yet, say in the report that the
app is behind its release). Never leave `### Unreleased` after a release, nor rename it without one.

- The assistant and the MCP server update themselves from `main` when they start, so their users get every merged
  PR without a release: what is under `### Unreleased` in the changelog.
- The QGIS plugin reaches users through plugins.qgis.org, so only with a release.
- The R and Python packages install from GitHub (`main` or a tag).
- The Earth Engine app is published after asking (step 7): `python gee/push_app.py` pushes it to its repository in
  Earth Engine and to the backup, and the Code Editor updates the app from `users/monitoreo-obsnev/monitoreo:app`
  (see the wiki page Earth-Engine-app, "For administrators").
- Zenodo gets a new version, with its own DOI, for each GitHub release. Its creators, contributors (with ORCIDs) and
  references come from `.zenodo.json`, and `CITATION.cff` has to match it (`tests/test_references.py` checks both).
