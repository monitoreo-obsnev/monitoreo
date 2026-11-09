# MonitorEO (monitoreo)

For any change to this repository (code, catalog of variables, tools, tests, documentation or a release), follow the
team's methodology in the skill `monitoreo-change` (`.claude/skills/monitoreo-change/SKILL.md`):

- a branch from `origin/main`, never commits on `main`;
- the change in every tool and in its help;
- references with DOI and units in UDUNITS;
- tests;
- the wiki, in Spanish and English, pushed to its `master` without asking again: right after the merge of its PR or,
  for documentation that the developer asked for without code, when it is done;
- a pull request to `main`, which the developer merges when it is ready (no pushes to `main`);
- after each merge that changes the package, the QGIS plugin or the app, a release (new versions and a tag), without
  asking again.

Ask before pushing, opening or merging a pull request, or publishing anything, except the wiki (after the merge of its
PR, or documentation asked for without code, when it is done), the release after a merge and the deletion of merged
branches. Say that it computes in Google Earth Engine, and with which project, before running anything that does.

The texts of the tools are in English. Answer the developer in their own language.
