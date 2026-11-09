# A release

Only when the developer asks for a release. The team decides when to release; a merged PR alone is not a release.

## Versions

There are two version numbers:

- **The package** `monitoreo` (Python and R): `pyproject.toml`, `src/monitoreo/__init__.py` (`__version__`) and
  `r/monitoreo/DESCRIPTION` (`Version:`), always the same.
- **The QGIS plugin**: `qgis/monitoreo_qgis/metadata.txt` (`version=`).

The **tag** of a release is the plugin's version (`v0.3.15`). The workflow `qgis-plugin.yml` fails if they differ.
Raise both by one patch step unless the developer says otherwise. The last releases are in `git tag --sort=-v:refname`.

## Steps

1. A branch `release-<plugin version>` from an up-to-date `origin/main`.
2. One commit that raises the four files. Subject: `monitoreo <package version> and QGIS plugin <plugin version>:
   <what users get, in a few words>`.
3. Check what the workflows will check:
   - the offline tests;
   - `python qgis/build_plugin.py`, which needs internet; with `bandit` and `detect-secrets` installed it runs the same
     security scan as plugins.qgis.org;
   - `metadata.txt` must have no `%` (plugins.qgis.org cannot read it).
4. Open the PR of the release, like any other change, and wait for it to be merged.
5. After the merge, and after asking: push an annotated tag on the merge commit,
   `git tag -a v<plugin version> -m "MonitorEO <plugin version>"` and `git push origin v<plugin version>`. The workflows
   then create the GitHub release (`qgis-plugin.yml` attaches the plugin zip and uploads it to plugins.qgis.org;
   `installers.yml` attaches the assistant installers), and Zenodo archives the release with the metadata of
   `.zenodo.json`.
6. Check the release on GitHub. Uploads to plugins.qgis.org wait for a volunteer's approval.

## Who gets what, and when

- The assistant and the MCP server update themselves from `main` when they start, so their users get every merged
  PR without a release.
- The QGIS plugin reaches users through plugins.qgis.org, so only with a release.
- The R and Python packages install from GitHub (`main` or a tag).
- The Earth Engine app is published by hand in the Code Editor (see the wiki page Earth-Engine-app, "For
  administrators"), after asking.
- Zenodo gets a new version, with its own DOI, for each GitHub release. Its creators, contributors (with ORCIDs) and
  references come from `.zenodo.json`, and `CITATION.cff` has to match it (`tests/test_references.py` checks both).
