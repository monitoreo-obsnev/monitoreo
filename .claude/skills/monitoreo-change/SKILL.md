---
name: monitoreo-change
description: The MonitorEO team's methodology for every change to this repository (monitoreo-obsnev/monitoreo: the Python package monitoreo, its CLI, MCP server and assistant, the QGIS plugin, the R package, the Earth Engine app in gee/, the results viewer and the catalog of variables). Use it whenever you are about to add, fix, change or document anything here — a new variable, sensor or formula in the catalog, a new tool, option or output, a bug fix, wiki documentation, a release — and before committing, pushing or opening a pull request, even if the developer only says "add X", "fix this" or "sube el cambio" and never mentions branches, tests or docs.
---

# Changing MonitorEO

MonitorEO is one computation (`monitoreo.services`) offered through many tools: the Python package and its command
line, the MCP server, the assistant for managers, the QGIS plugin, the R package, the Earth Engine app (a JavaScript
port in `gee/`) and the results viewer. Several people change it at the same time. The defects that reach users are
almost never in the line someone meant to change. They come from what nobody remembered to change:

- a variable added to the catalog but not to the help of the tools or to the wiki;
- a tool that knows a new option while the others do not;
- a code path that assumes every variable has dates, and fails on one that does not;
- a branch that merges cleanly as text but breaks what main added meanwhile.

This skill is the checklist the team agreed on, so that every change made with Claude lands the same way. Follow it
in order, and tell the developer what you are doing at each step, in their language.

## 1. Ground rules

- **Never commit on `main`.** Use one branch per piece of work. Changes reach `main` only through a pull request on
  GitHub (team decision, 2026-11-09), because other people are working on `main` at the same time.
- **Ask before anything that leaves this computer**: pushing a branch, opening or merging a PR, pushing the wiki,
  updating the Earth Engine app in the Code Editor or deploying the broker. Show what will be published, then wait for
  a clear yes. An approval covers only the step it was given for. The one exception is the release that follows a
  merge (next rule): the team approved it once for all.
- **A release after every merge** (team decision, 2026-11-09). As soon as a PR that changes what users get is merged
  (anything under `src/`, `qgis/`, `r/` or `gee/`, or the catalog), make a release with `references/release.md`: new
  versions, their PR, its merge and the tag, without asking again; then tell the developer. The QGIS plugin reaches its
  users only through releases. A PR that only changes the docs, the tests, the workflows or this skill waits for the
  next release, and a stack of PRs merged together gets one release after the last of them.
- **Say where it computes.** Everything computes in Google Earth Engine. Before you run anything that computes (`pytest -m ee`,
  `qgis/test_plugin.py`, `gee/build.py`, the CLI, MCP tools), say so and name the account and project it will use (the
  developer's `EE_PROJECT`, or the shared MonitorEO account `ee-ugr-default-project` when there is no project). The
  quota belongs to everyone.
- **Languages.** The texts of the tools are in English. The wiki is written in Spanish and English, with every page
  in both. Answer the developer in the language they write in.
- **Never invent a reference, a DOI or a unit.** If a source is unknown, ask the team; the catalog has a `PENDING`
  mechanism for that (see `references/new-variable.md`).

## 2. Start the branch

```bash
git fetch origin
git status --short          # unrelated changes? ask before mixing them in
git switch -c <topic> origin/main
```

Name the branch after the change in short kebab-case, in English: `ndmi-sentinel2`, `fix-assistant-static-maps`,
`cli-variables-json`. Start from `origin/main`, never from another feature branch, unless the developer asks for it.
Stacked branches drag unmerged work into the PR, as `elevation-slope` did with `snow-cover-frequency`.

## 3. Find what the change touches

Decide what kind of change it is, then read the reference that applies before you edit anything:

| The change | Read |
|---|---|
| A new variable, sensor, formula or special behaviour in the catalog | `references/new-variable.md` |
| A new tool, function, argument, option or output field, or a change of behaviour | `references/tool-parity.md` |
| A bug fix | `references/tool-parity.md`: the same bug usually lives in the other tools too |
| Documentation only | `references/docs.md` |
| A release (new versions, tag, Zenodo) | `references/release.md` |

**First check that it does not exist already.** Search the catalog (`catalog.variables()`: the same collection and
formula, maybe under another index), `services`, the tools and the wiki for what is being asked. Someone may ask for an
index the catalog already has under another name. The NDMI of Sentinel-2 is `N(B8,B11)`, which is exactly the LSWI of
Sentinel-2. They may also ask for an option that a tool already has. If you find it, stop and tell the developer
before building anything, and propose the options: use what exists, document the other name, or add an alias. A
duplicate entry is easy to add and hard to remove once users and reports depend on it.

Most changes touch more places than they seem to. Before editing, list them for the developer: the files, the tools,
the tests and the wiki pages you will change. Then they can say if something is missing or out of scope.

## 4. The rules every change keeps

These are the invariants of MonitorEO. Tests check some of them; the rest depend on you.

- **One computation, every tool.** New behaviour goes into `monitoreo.services` and reaches every tool that exposes that
  function: the CLI, the MCP server, the assistant, the QGIS plugin, the R package, the Earth Engine app and the viewer.
  If a tool cannot have it, say why in the PR. For example, the shared account cannot export to Google Drive.
- **Everything is cited.** Every variable, algorithm, method and Earth Engine dataset has its references in
  `catalog.json`: APA citations with a DOI, and each dataset cited as its page of the Earth Engine catalog suggests,
  with the credit line its terms of use ask for. Verify every DOI at doi.org before you use it. After adding
  references, regenerate the references of `.zenodo.json` (`references/new-variable.md` says how).
- **Every unit is in UDUNITS.** Each unit of the catalog has its UDUNITS name in `catalog.UDUNITS`. The degree sign is
  `°` (U+00B0), never the ordinal `º`.
- **Every file explains itself.** Every file a tool writes gets a README and metadata (`readme.py`, `report.py`):
  what each column or band is, with its unit, how it was computed, how to reproduce it and how to cite it. If you add
  an output or a kind of variable, read the README it produces.
- **Special variables reach every code path.** Some variables behave differently: fixed layers without dates
  (ELEVATION, SLOPE), a single metric and fixed pixel filters (SCF), or two periods (RBR). Grep for every place that
  reads `start`, `end`, `metric` or `quality` and check that it copes. The assistant's `KeyError: 'start'` of
  2026-11-09 was a single path that did not.
- **Everything has a theme.** The QGIS plugin and the Earth Engine app show the catalog by themes (`catalog.THEMES`):
  the user chooses a theme (Vegetation, Water, Snow, Fire, Energy and temperature, Atmosphere, Climate, Terrain) and
  then sees its variables and its own analyses. A new variable goes into the theme it belongs to. An analysis of one
  kind of variable (like `burn_severity` for the fires) goes in the `analyses` of its theme, so the menus show it only
  there. A new kind of functionality (e.g. species distribution models) gets a new theme, with its variables and
  analyses, in both menus. Never leave a variable or an analysis outside the themes: users would not find it.
- **Tests come with the change.** Add or adjust a test in `tests/` for each behaviour you add or fix. For a bug, write
  the test that reproduces it first.

## 5. Check before the pull request

Run the checker of this skill first. It looks at the branch, the conflicts with `main`, the catalog (references, units,
the Earth Engine app, the wiki) and the generated files (R help, versions):

```bash
python .claude/skills/monitoreo-change/scripts/check_change.py
```

Then, as the change requires:

- **Offline tests** (no Earth Engine, no network). They need a Python with `earthengine-api` (the environment of
  `environment.yml`):
  `PYTHONPATH=src python -m pytest tests -q`. `qgis/test_plugin.py` needs QGIS and is not part of these.
- **R help.** If the roxygen comments in `r/monitoreo/R/monitoreo.R` changed, regenerate the help and commit
  `r/monitoreo/man/`:
  `Rscript -e 'roxygen2::roxygenise("r/monitoreo", roclets = c("rd", "namespace"))'`.
- **The Earth Engine app.** It carries its own copy of the catalog. If `catalog.json`, `catalog.py`, `about.py` or
  `gee/*.js` changed, rebuild it with `python gee/build.py --project <project>`. This computes in Earth Engine, so say
  so first. If you cannot run it, edit only trivial values (a unit, a text) by hand in both `gee/catalog.js` and
  `gee/monitoreo_app.js`, and write in the PR that a rebuild is pending. Publishing the app in the Code Editor is a
  separate, approved step after the merge.
- **Tests with Earth Engine.** If a computation changed, run `EE_PROJECT=<project> python -m pytest -m ee`, after
  asking. If you did not run them, say so in the PR.
- **The QGIS plugin.** If `qgis/` changed, run its test with the Python of QGIS (see the wiki page Development), or say
  that it was not run.
- **Bring `main` into the branch** just before opening the PR, and again if `main` moves while the PR is open:

  ```bash
  git fetch origin && git merge origin/main
  ```

  Merge; don't rebase (the history uses merge commits). Resolve text conflicts by keeping both sides. Then run the
  tests again and think about **semantic conflicts**: code from `main` that now has to cover your feature, or your
  feature now needing what `main` added. A clean text merge proves nothing about this. Every unhandled case that turns
  up is a fix for this same PR.

## 6. Document it

- Documentation lives in the **wiki**, a separate git repository (`git@github.com:monitoreo-obsnev/monitoreo.wiki.git`;
  the team keeps its clone next to this repository, in `../monitoreo.wiki`), with every page in Spanish and English.
  `references/docs.md` has the page pairs and what goes where.
- `README.md` changes only for the table of tools, how to cite and the acknowledgements.
- The wiki has no pull requests. Prepare the pages on a wiki branch with the same name as the code branch, and push
  them to the wiki's `master` once the PR is merged, after asking.
- The assistant answers from the wiki (`manual.py` searches it), so what is not in the wiki does not exist for its
  users.

## 7. Commit, push and open the pull request

- **Commit messages** follow the style of the history, in English. The subject is a sentence that says what users get,
  without a type prefix. For example: "The assistant with the fixed layers: the map of the elevation and of the slope,
  and their pixels". The body says why, and what was not verified. End it with the co-author line the harness gives.
- **Push the branch**, after asking: `git push -u origin <branch>`. If HTTPS has no credentials, push to
  `git@github.com:monitoreo-obsnev/monitoreo.git <branch>`.
- **Open the pull request** against `main` with the checklist of `.github/PULL_REQUEST_TEMPLATE.md`, ticking only what
  was actually done. For each item that does not apply, write "n/a" and why. If your branch does not have the
  template, read it from `main` (`git show origin/main:.github/PULL_REQUEST_TEMPLATE.md`). Use
  `gh pr create --base main --head <branch>` if `gh` is signed in. If not, write the body to a file and give the
  developer the link `https://github.com/monitoreo-obsnev/monitoreo/compare/main...<branch>?expand=1`, where GitHub
  fills the body from the template.
- **Merge it when the developer says so** (team decision, 2026-11-09: whoever opens a PR may merge it; nobody else has
  to review it first). Check first that GitHub can merge it (`gh pr view <n> --json mergeable`), that `main` is merged
  in and the tests pass; for stacked PRs, merge them in order. Use a merge commit, as the history does:
  `gh pr merge <n> --merge --delete-branch`. **Never push to `main`**: everything reaches it through a PR.
- **After the merge**, when `git fetch origin` shows it in `main`:
  - make the release, if the PR changed what users get (`references/release.md`);
  - push the wiki branch to `master`, after asking;
  - if the catalog, `about.py` or `gee/` changed, offer to update the Earth Engine app in the Code Editor.
- **Merged branches are always deleted** (team decision, 2026-11-09):
  - **The code branch on GitHub.** The workflow `.github/workflows/delete-merged-branch.yml` deletes it when its PR is
    merged. If it is still there, delete it: `git push origin --delete <branch>`.
  - **Locally**, delete the branch, and the clone's own copy:

    ```bash
    git switch main && git pull --ff-only
    git branch -d <branch>
    git worktree remove <path>   # only if the work had a worktree of its own
    ```

    `git branch -d` refuses a branch that is not merged. Do not force it with `-D`: if it refuses, look at what is
    missing first.
  - **The wiki branch**, local and remote, once it is merged into the wiki's `master`.
  - Set `git config fetch.prune true` in both clones, so that `git fetch` forgets the branches deleted on GitHub.

## 8. Report

End with a short report for the developer:

- the branch, its commits and the PR link (or the compare link);
- the tests you ran and their result;
- what was not verified (Earth Engine, QGIS, the rebuild of the Earth Engine app) and why;
- what is still pending: the wiki push, the Earth Engine app, and the release if it is not made yet.

Saying plainly what was not checked is part of the method. A reviewer needs to know where to look.
