# A new function, option or output, a change of behaviour, or a bug fix

Every tool calls the same `monitoreo.services`. A feature is finished only when each tool that exposes the function
offers it, and when its results describe and cite themselves. A bug in `services` reaches every tool. A bug in one
tool's code often has a twin in another.

## Where a function of `services` appears

| Layer | File | What to update |
|---|---|---|
| The computation | `src/monitoreo/services.py` (helpers in `variable.py`, `composite.py`, `trends.py`, `fire.py`, `maps.py`...) | the function and its docstring; `_cited` adds references and the README to the results that write files |
| Citations | `src/monitoreo/references.py` | a new tool that computes goes in `EARTH_ENGINE` (and in `TRENDS` if it computes trends); a new method gets its references in `methods` of `catalog.json` |
| Files and their README | `src/monitoreo/readme.py`, `src/monitoreo/report.py` (`TITLES`, `METHODS`, `item_facts`), `src/monitoreo/publish.py` (`default_title`) | a title, the facts of how it was computed and the method, for every new tool or output |
| Command line | `src/monitoreo/cli.py` | a subcommand or option (`sub.add_parser`) |
| MCP server | `src/monitoreo/mcp_server.py` | a `@tool` function, with a docstring for the model; the summary of its answer keeps `readme`, `references` and `credits` (read optional keys with `res.get(k)`, never `res[k]`); `INSTRUCTIONS` if the workflow changes |
| Assistant for managers | `src/monitoreo/assistant.py`, `src/monitoreo/ui/assistant.html`, `src/monitoreo/steps.py` | which list the tool goes in: `RESULTS` (to the page, not to the model), `ADVICE` (to the model) or `TASKS`; `HIDDEN` arguments; the prompt (`PROMPT`); the card, maps, steps and pixels of its results |
| QGIS plugin | `qgis/monitoreo_qgis/dock.py`, `results.py`, `helptexts.py` | the widget, the arguments sent (`variable_args`), the result window, the help text |
| R package | `r/monitoreo/R/monitoreo.R` | an `mo_*` function with roxygen (`@inheritParams mo_params`, `@return`, `@section References`, `@export`) that calls `services()$...` and returns its attributes with `cited()`; then regenerate `man/` and `NAMESPACE` with roxygen2; a test in `r/monitoreo/tests/testthat` |
| Earth Engine app | `gee/core.js` (computation), `gee/ui.js` (interface), then `gee/build.py` | the port, if the app offers the function; `tests/test_gee.py` checks it gives the same values as Python |
| Results viewer | `src/monitoreo/publish.py`, `src/monitoreo/viewer/assets/*.js` | if the new result can be published |
| Downloads of variables | `src/monitoreo/recipe.py` | if a recipe can ask for it |

Not every function belongs in every tool. Drive exports need the user's own account, and only the assistant has the
pixel queries. Decide with the developer, and write the decision in the PR.

## Rules for new behaviour

- **Optional keys are optional everywhere.** When you add a key to a result (`ylabel`, `readme`, `references`...), the
  consumers built before it must not break on results without it. Read it with `.get`. The merge of PR #3 broke
  `trend_table` in the MCP server on exactly this.
- **Arguments a variable does not have.** Fixed layers have no `start`, `end`, `metric` or pixel filters. Single-metric
  variables reject other metrics. Two-period variables refuse single-period tools. Any new code that reads those
  arguments must handle these cases. Grep the existing handling (`is_static`, `fixed_filters`, `two_periods`) and
  follow it.
- **Results describe themselves.** A new output file needs its README (`readme.py`) and GeoTIFF metadata. A new
  result needs a title and facts (`report.py`). Read the README of an example: no period for a layer without dates, no
  filters that were not applied.
- **English texts** in every tool, and the same names and wording in all of them.

## Bug fixes

1. Reproduce the bug first, with a test that fails (offline if possible: the tests fake Earth Engine and the MCP
   server, see `tests/test_assistant.py` and the `monkeypatch` of `services` in `tests/test_references.py`).
2. Fix it where it starts, usually in `services` or a shared helper, rather than patching one tool.
3. Grep for the same pattern in the other tools and fix the twins in the same branch.
4. If the user saw an error message, quote it in the commit body and the PR.
5. A bug that is the user's own mistake (a wrong argument) gets a clear message, not a traceback.

## Tests

- Python: `tests/test_offline.py` (catalog, services without Earth Engine), `tests/test_assistant.py` (assistant with
  a test model and a faked MCP server), `tests/test_references.py`, `tests/test_readme.py`, `tests/test_publish.py`.
  Tests marked `ee` compute in Earth Engine, and run only with `EE_PROJECT` set.
- R: `r/monitoreo/tests/testthat`, run with
  `RETICULATE_PYTHON=<python> PYTHONPATH=$PWD/src Rscript -e 'pkgload::load_all("r/monitoreo"); testthat::test_dir("r/monitoreo/tests/testthat")'`.
  The tests that compute in Earth Engine need `EE_PROJECT`.
- QGIS: `qgis/test_plugin.py`, with the Python of QGIS. It computes in Earth Engine.
