# MonitorEO (monitoreo)

For any change to this repository (code, catalog of variables, tools, tests, documentation or a release), follow the
team's methodology in the skill `monitoreo-change` (`.claude/skills/monitoreo-change/SKILL.md`):

- a branch from `origin/main`, never commits on `main`;
- before editing, the open PRs and the issues `in progress` of the others; then an issue `in progress` that announces
  this change (not for a release, for documentation alone, or when the developer said not to publish anything yet);
- the change in every tool and in its help;
- references with DOI and units in UDUNITS;
- tests;
- the wiki, in Spanish and English, pushed to its `master` without asking again: right after the merge of its PR or,
  for documentation that the developer asked for without code, when it is done;
- a pull request to `main`, which the developer merges when it is ready and the workflow Tests is green (no pushes to
  `main`);
- after each merge that changes the package, the QGIS plugin or the app, a release (new versions and a tag), without
  asking again, and only one release at a time;
- the Earth Engine app and the broker are published from `main`, after the merge.

Three people develop MonitorEO, each with their own Claude. The rules are those of `main`: on a branch that started
earlier, run `git fetch origin && git diff --stat HEAD...origin/main -- .claude/skills/monitoreo-change CLAUDE.md`,
and if `main` changed them, merge `origin/main` and read the skill again. Team decisions go into the skill or this
file through a PR, not into the personal memory of Claude, which the others do not see.

Ask before pushing, opening or merging a pull request, or publishing anything, except the issue that announces a
change, the wiki (after the merge of its PR, or documentation asked for without code, when it is done), the release
after a merge and the deletion of merged branches. Say that it computes in Google Earth Engine, and with which project,
before running anything that does.

The texts of the tools are in English. Answer the developer in their own language.
