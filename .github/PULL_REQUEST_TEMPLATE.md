## What it changes

<!-- What users get, and why. For a bug: the error users saw and how to reproduce it. Then "Closes #<n>", with the
issue "in progress" that announced this change (none for a release or for documentation alone). -->

## Checklist

<!-- Tick what was done; for what does not apply, write "n/a" and why. -->

- [ ] A branch from an up-to-date `main`, with `main` merged in again before this PR; the tests pass after that merge
- [ ] Offline tests pass: `PYTHONPATH=src python -m pytest tests -q -m "not ee"`, and the workflow **Tests** of this
      PR is green
- [ ] Tests added or updated for what changes
- [ ] Every tool that exposes the function has it (command line, MCP server, assistant, QGIS plugin, R package, Earth
      Engine app, field app, results viewer), or the reason why not is written here
- [ ] New variables, methods or datasets: references with DOI in `catalog.json`, the datasets with their credit line,
      and the references of `.zenodo.json` regenerated
- [ ] Units in UDUNITS (`catalog.UDUNITS`)
- [ ] Each new variable or analysis in its theme (`catalog.THEMES`), the menus of the QGIS plugin and the Earth Engine app
- [ ] The README and metadata of the files it writes read right
- [ ] R help regenerated with roxygen2 (`r/monitoreo/man`), if the roxygen changed
- [ ] Earth Engine app rebuilt (`gee/build.py`), if the catalog, `about.py` or `gee/` changed
- [ ] Its entries, in English, under `### Unreleased` in the changelog of `README.md` (or n/a: users do not notice it)
- [ ] Wiki pages in Spanish and English (wiki branch: `...`)
- [ ] Texts of the tools in English

## Not verified

<!-- What was not run or checked, and why: tests with Earth Engine (pytest -m ee), the QGIS plugin test, the rebuild or
the publication of the Earth Engine app... -->

## Check of the branch

<!-- Optional: the output of `python .claude/skills/monitoreo-change/scripts/check_change.py` -->
