# Documentation

## Where it goes

- **The wiki** of `monitoreo-obsnev/monitoreo` holds the manual of every tool, the concepts and the notes for
  developers. It is a git repository of its own, with a flat folder of Markdown pages and only the branch `master`:

  ```bash
  git clone git@github.com:monitoreo-obsnev/monitoreo.wiki.git ../monitoreo.wiki   # once, next to this repository
  ```

- **`README.md`** has only the table of tools (with links to their wiki pages), how to cite (DOI) and the
  acknowledgements with the logos, first in Spanish and then in English. Touch it only to add a tool to the table or
  to change the citation or the acknowledgements.
- **Docstrings and roxygen** document functions for programmers (`help()` in Python, `?mo_...` in R). They are
  written in English, and the R help is regenerated with roxygen2.
- **The assistant** answers questions about MonitorEO by searching the wiki (`src/monitoreo/manual.py`). A feature
  missing from the wiki is a feature the assistant cannot explain.

## Two languages

Every Spanish page has its English page, and each page links to the other at the top. Write each new section in both,
with the same content:

| Spanish | English |
|---|---|
| Home | English |
| Primeros-pasos | Getting-started |
| Instalación-paso-a-paso | Step-by-step-installation |
| Conceptos | Concepts |
| App-de-Earth-Engine | Earth-Engine-app |
| QGIS | QGIS-plugin |
| MCP | MCP-server |
| Asistente | Assistant |
| Python | Python-package |
| Línea-de-comandos | Command-line |
| R | R-package |
| Visor-de-resultados | Results-viewer |
| Problemas-frecuentes | Troubleshooting |
| Desarrollo | Development |

`_Sidebar.md` and `_Footer.md` are bilingual.

## What to document for each kind of change

- **A variable**: `Conceptos`/`Concepts` (the table of variables, and its section in "what each variable measures",
  with its reference and DOI), and `Home`/`English` if they list the variables. See `new-variable.md`.
- **A function or option**: the page of each tool that offers it (Python, Command line, MCP, Assistant, QGIS, R,
  Earth Engine app), with an example of its use. The same example in every tool helps users move between them.
- **A concept** (a method, a filter, a kind of file): its section in `Conceptos`/`Concepts`, with references.
- **For developers** (where code lives, how to test, how to publish): `Desarrollo`/`Development`.
- **Errors users may meet**: `Problemas-frecuentes`/`Troubleshooting`.

## How to publish it

GitHub only shows the wiki's `master`, and the wiki has no pull requests. So:

1. In `../monitoreo.wiki`, `git fetch && git switch -c <same name as the code branch> origin/master`.
2. Edit the Spanish and English pages, and commit, with a message in the language of the page edited (the history mixes
   both).
3. Mention the wiki branch and its pages in the code PR, so the reviewer can read them.
4. When the code PR is merged: fetch, check the branch merges into `origin/master` without conflicts, merge it, and
   push `master` after asking the developer. Pushing the wiki before the code is merged documents something users
   don't have yet.
