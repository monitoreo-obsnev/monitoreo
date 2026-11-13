# A new variable, sensor or formula in the catalog

A variable lives in the catalog, but users meet it through every tool, its help, its files and the wiki. Work through
this list in order. Tick off each item, or say why it does not apply.

## 0. Is it there already?

List the entries of the same sensor and compare their formulas (`ft`, `f`) with the one asked for:

```bash
PYTHONPATH=src python -c "from monitoreo import catalog; [print(e['ref'], e['index'], e['sensor'], e['ft'], e.get('f')) for e in catalog.variables()]"
```

An index often has several names in the literature. For example, the NDMI and the LSWI are the same normalized
difference of NIR and SWIR1. If the formula is already there, stop and ask the developer before adding anything (see
step 3 of `SKILL.md`).

## 1. The entry

- **A plain variable** (a band, an expression of bands, or a normalized difference `N(b1,b2)` of a collection) is an
  entry of `variables` in `src/monitoreo/catalog.json`, which is maintained by hand. Copy the closest existing entry
  (same sensor and collection) and change it. `fields` at the top of the file says what each field is. The ones that
  matter most:
  - `ref`: the next free ID;
  - `index`: the short name users type, e.g. `NDMI`;
  - `sensor`: `Sentinel-2`, `Landsat` or `Modis`;
  - `col` (`LANDSAT` means Landsat 5, 7, 8 and 9), `m` (native pixel size) and `dr` (dates);
  - `ft`, the formula with band names (`N(nir,swir1)`), and `f`, the same with the real band names;
  - `scale` and `offset` of the bands;
  - the QA bands of each filter (`*_bandQA`);
  - `unit`, and the colour ramp `minp`, `maxp`, `pm`;
  - the names in each language (`vname` in Spanish, `vname_en`, `vname_fr`, `vname_de`) and the group (`type`, `type_en`...);
  - `large_areas`;
  - `references`.
- **A variant of an existing entry** (another index from the same bands, a fixed layer, a template shared by several
  sensors) goes in `catalog.EXTRA`, with its fields in `catalog.TEMPLATES`, as NBR, RBR, SCF, ELEVATION and SLOPE do
  (refs 101 to 107), and the RdNBR (refs 144 to 147, two periods like the RBR, also of MODIS). `EXTRA` copies the base
  entry, then applies the template, then the changes.
- **A new kind of formula** (anything `sensors.parse_formula` cannot read, like `SCF(green,nir,swir1)`) needs its code
  in `sensors.py`, its port in `gee/core.js`, and a test of both in `tests/test_gee.py` (that test computes in Earth
  Engine).
- **A new special behaviour** (no dates, a single metric, fixed filters, two periods...) needs:
  - a new field in `fields`, explained there;
  - the check in every code path. Find how the closest existing one is handled, e.g. `git grep -n "static"` or
    `git grep -n "fixed_filters"`. A path you do not change is a path that can crash. Look at least at:
    - `services.py` and `variable.py` (specs and validation);
    - `report.py`, `publish.py` and `readme.py` (titles, facts, README);
    - `assistant.py` (cards, map labels, pixels, steps);
    - `steps.py`;
    - `qgis/monitoreo_qgis/dock.py` (which widgets are greyed out, which arguments are sent);
    - `gee/ui.js` and `gee/core.js`;
    - the R functions.
- **The count of variables** in `tests/test_offline.py::test_catalog` (`assert len(entries) == ...`) goes up by one,
  with a comment saying what was added.
- **Its theme.** Add its index to the `indices` of its theme in `catalog.THEMES` (the menus of the QGIS plugin and
  the Earth Engine app, and the `theme` of `list_variables`). If none fits, propose a new theme to the team, with its
  names in English and Spanish; `check_change.py` fails on a variable without a theme.

## 2. References and credits

Each variable is cited: the article of its formula or algorithm, its Earth Engine datasets and its pixel filters.
`tests/test_references.py` fails without them.

- **The formula or algorithm**: list the IDs in the entry's `references` (e.g. `["gao1996"]`), and add each new ID to
  `references` in `catalog.json`: `{"citation": "<APA, without the DOI>", "doi": "10.xxxx/..."}`. IDs are the first
  author's surname and the year, lowercase (`hall1995`). Check every DOI and its citation at doi.org (content
  negotiation: `curl -sLH "Accept: application/vnd.citationstyles.csl+json" https://doi.org/<doi>`).
- **A new Earth Engine collection** goes in `datasets`: `{"references": [...], "credit": "..."}`, cited as its page in
  the Earth Engine catalog says (its Citations and DOI), with the credit line its terms of use ask for (e.g. Copernicus,
  USGS). Without a credit requirement, leave `credit` out.
- **Other datasets the algorithm reads** (e.g. the SRTM and the Landsat TOA scenes used by the SCF) do not come from
  `col`. Add them in `references.of_variable` so they are cited, and add them to `datasets` too.
- **No source found**: never invent one. Leave `references` empty, explain in `notes.references` what is missing, add
  the `ref` to `PENDING` in `tests/test_references.py`, and tell the developer that the team has to find it.
- Then regenerate the bibliography of Zenodo (`test_zenodo_metadata` checks it):

  ```bash
  PYTHONPATH=src python -c "import json; from monitoreo import references; z = json.load(open('.zenodo.json', encoding='utf-8')); z['references'] = references.bibliography_texts(); open('.zenodo.json', 'w', encoding='utf-8').write(json.dumps(z, indent=2, ensure_ascii=False) + '\n')"
  ```

- Add a line to `test_cite` in `tests/test_references.py` that checks the new IDs appear for a call with the new
  variable.

## 3. Units and pixel filters

- The unit of the entry (`[unitless]`, `[°C]`, `[%]`, `[m]`, `[°]`...) needs its UDUNITS name in `catalog.UDUNITS`.
  `tests/test_readme.py::test_units` fails without it. Use the degree sign `°`, not the ordinal `º`.
- Check the pixel filters make sense for the variable. A variable that measures what a filter removes (snow, water)
  needs `"auto"` or fixed filters, and the assistant's prompt must say so (see NDSI, NDWI and SCF).

## 4. The help of every tool

Lists of variables are written out in several places. Find them all, in this repository and in the wiki:

```bash
git grep -n -E "LSWI, NDSI|NDVI, EVI" -- . ':!gee/*.js'
grep -n -E "LSWI, NDSI|NDVI, EVI" ../monitoreo.wiki/*.md
```

and add the new variable where it belongs:

- `src/monitoreo/mcp_server.py`: `INSTRUCTIONS`, the list of variables, plus a sentence on how to use it if it is
  special;
- `src/monitoreo/assistant.py`: the prompt (`PROMPT`), with the sensor guide and how to ask for the variable (its
  sensor, metric, filters, dates);
- `qgis/monitoreo_qgis/metadata.txt`: `about=`. No `%` sign in it: plugins.qgis.org rejects the file;
- `qgis/monitoreo_qgis/helptexts.py`, if the variable needs an explanation in the plugin;
- `r/monitoreo/DESCRIPTION` (`Description:`), and the roxygen in `r/monitoreo/R/monitoreo.R` if it adds a sensor or
  arguments (`mo_params`). Then regenerate `man/` with roxygen2.

## 5. The Earth Engine app and the viewer

- Rebuild the app: `python gee/build.py --project <project>`. It computes in Earth Engine, so say so first. Commit
  `gee/catalog.js` and `gee/monitoreo_app.js`.
- For a special behaviour, also update `gee/ui.js`, and `gee/core.js` if the computation differs.
- Charts: if the axis title is not just the unit, give the entry an `axis` (as the SCF does). `ylabel` then carries it
  to the charts of every tool and of the viewer (`src/monitoreo/viewer/assets/charts.js`).

## 6. Tests

At least:

- the entry in `tests/test_offline.py` (its fields, `catalog.find(index, sensor)`, its unit, and its special behaviour
  if it has one);
- its references in `tests/test_references.py`;
- the README of a result of the new variable, if it is special, in `tests/test_readme.py`;
- if it has a new formula: its parity with the Earth Engine app in `tests/test_gee.py`.

Run the offline tests, and the checker of the skill.

## 7. The wiki

In both `Conceptos.md` and `Concepts.md`:

- a row in the table of `## Variables`;
- a subsection in `## Qué mide cada variable` / `## What each variable measures`, saying what it measures, its formula,
  its range and how to read it, and its reference with a DOI link;
- for a special behaviour, a sentence where it applies (filters, maps, trends).

Also update `Home.md` / `English.md` if they list the variables, and the page of each tool where its use differs.
Follow `references/docs.md`.

## 8. In the PR

Say:

- which entry or entries you added (`ref`, `index`, `sensor`);
- its references with their DOIs;
- whether the Earth Engine app was rebuilt;
- which tests ran.

The variable reaches users of the assistant and the MCP server when the PR is merged into `main` (they update from
GitHub), the QGIS plugin with the next release, and the Earth Engine app when it is published in the Code Editor.
