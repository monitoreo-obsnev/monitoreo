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

The **tag** of a release is the plugin's version (`v0.3.15`). The workflow `qgis-plugin.yml` fails if they differ.
Raise both by one patch step unless the developer says otherwise. The last releases are in `git tag --sort=-v:refname`.

## Steps

1. A branch `release-<plugin version>` from an up-to-date `origin/main`.
2. One commit that raises the four files and gives the release its entries in the changelog of `README.md`: rename
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

## Who gets what, and when

- The assistant and the MCP server update themselves from `main` when they start, so their users get every merged
  PR without a release: what is under `### Unreleased` in the changelog.
- The QGIS plugin reaches users through plugins.qgis.org, so only with a release.
- The R and Python packages install from GitHub (`main` or a tag).
- The Earth Engine app is published by hand in the Code Editor (see the wiki page Earth-Engine-app, "For
  administrators"), after asking.
- Zenodo gets a new version, with its own DOI, for each GitHub release. Its creators, contributors (with ORCIDs) and
  references come from `.zenodo.json`, and `CITATION.cff` has to match it (`tests/test_references.py` checks both).
