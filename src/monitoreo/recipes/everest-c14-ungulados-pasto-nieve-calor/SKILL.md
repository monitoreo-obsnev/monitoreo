---
name: everest-c14-ungulados-pasto-nieve-calor
description: Mountain ungulates (Iberian ibex, Pyrenean and Cantabrian chamois) and their pastures in four Spanish national parks (Sierra Nevada, Picos de Europa, Ordesa y Monte Perdido, Aigüestortes). Yearly green-up calendar (MODIS MCD12Q2 by its ID), snow melt-out day and snow cover days (MOD10A1), July-August land surface temperature (MOD11A1, Terra) and MODIS NDVI of the treeless pastures above 1,800 m, 2001-2025, with Hamed-Rao trends by elevation band, standardized spring anomalies, a period comparison and correlations with ibex recruitment from open census data (GBIF). Use it to repeat this case or to build a yearly «good or bad pasture year» satellite indicator for any mountain herbivore. Partial results, no open chamois data; only the Iberian ibex of Sierra Nevada was tested.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  park: Sierra Nevada, Picos de Europa, Ordesa y Monte Perdido, Aigüestortes i Estany de Sant Maurici national parks
  wdpa_id: "389011, 71213, 893, 196014"
  event: "C14 (EVEREST case study)"
  event_date: "2001-2025 (yearly)"
  disturbance: other
  status: partial
  monitoreo_version: "0.3.96"
---

# Mountain ungulates: pasture phenology, snow and summer heat in four Spanish national parks, 2001-2025

> **Versions of MonitorEO.** Computed with MonitorEO 0.3.96, before 0.3.99. Since 0.3.99 a variable of MODIS of the
> catalog is reduced, at its resolution, on the sinusoidal grid of its products (not on pixels of 250-1000 m of the
> UTM zone; data given by collection and band are not); the LST of MODIS has a snow filter on by default (`quality:
> {"snow": false}` for the LST as it was): a repetition gives slightly different MODIS values. The overpass of MODIS
> Terra drifts earlier since 2022 (in 2025 about 9.8 h by day and 20.8-20.9 h by night, local solar time, instead of
> about 11 h and 22 h): trends of its LST that include 2022 or later lean cooler by day and warmer at night; compare
> them with those up to 2021, and check the bands Day_view_time and Night_view_time.

> **Files of this recipe.** `<everest>` is the folder of the EVEREST project where this case was computed. Its local scripts (`resultados/casos/C14/scripts/`) and the census file
> from GBIF are not part of MonitorEO. Everything else is the MonitorEO calls below, which can be repeated as they are.

## Question
Do the date and speed of spring green-up, the snow melt-out and the summer heat explain the year-to-year variation of
recruitment and body condition of Iberian ibex (*Capra pyrenaica hispanica*, Sierra Nevada) and chamois (*Rupicapra
pyrenaica*, Picos, Ordesa, Aigüestortes)? It informs hunting quotas and the grazing of summer pastures with a satellite
indicator available in July, and the anticipation of mange-risk years.

## Region and periods
- Region: the four parks in one call, `{"wdpa_id": [389011, 71213, 893, 196014]}` (one series per park).
- Treeless high pastures: `where` = `[{"variable": "ELEVATION", "sensor": "Copernicus", "min": 1800},
  {"variable": "TREE_COVER", "sensor": "Hansen", "max": 10}]`; elevation bands with `min`/`max` 1800-2200,
  2200-2600 and ≥ 2600 (Picos has no pixels ≥ 2600 m with these filters). Spatial statistic: `stat: "median"`.
- No control: the comparison is between years and between bands. Reference for z: 2001-2020.
- Periods: 2001-2024 for MCD12Q2 (its last year in the catalog copy was 2024), 2001-2025 for snow and LST, spring
  window 1 April-15 July (what is known in July), summer 1 July-31 August for the LST, 13 August-30 September for
  senescence.
- Sensors: MODIS only (250 m-1 km), the only sensor with daily revisit since 2000 for snow and LST and a yearly
  phenology product; Terra only for the LST (do not mix Terra and Aqua overpass times).

## Steps
All calls are in `<everest>/resultados/casos/C14/llamadas.json` (ids in brackets) and were run with
`herramientas/mcp_calls.py`. `R` = the region and `W` = the `where` above.

1. Check the images [`ic_ndvi`, `ic_lst`]:
   ```json
   {"tool": "image_count", "args": {"region": R, "variable": "NDVI", "sensor": "Modis", "collection": "MODIS/061/MOD13Q1",
    "start": "2001-01-01", "end": "2025-12-31", "step": "annual", "where": W}}
   {"tool": "image_count", "args": {"region": R, "variable": "LST", "sensor": "Modis", "collection": "MODIS/061/MOD11A1",
    "start": "2001-01-01", "end": "2025-12-31", "step": "annual", "season": ["07-01", "08-31"], "where": W}}
   ```
2. Green-up calendar from MCD12Q2 by its ID (`describe_asset` first), one call per band [`mcd_greenup_1`,
   `mcd_midgreenup_1`, `mcd_maturity_1`, `mcd_peak_1`, `mcd_senescence_1`]:
   ```json
   {"tool": "time_series", "args": {"region": R, "collection": "MODIS/061/MCD12Q2", "band": "Greenup_1", "unit": "d",
    "start": "2001-01-01", "end": "2024-12-31", "step": "annual", "metric": "mean", "stat": "median", "where": W}}
   ```
   plus `EVI_Amplitude_1` with `"band_scale": 0.0001, "unit": "1"` [`mcd_evi_amplitude_1`] and `QA_Overall_1` with
   `"unit": "1", "stat": "mean"` [`mcd_qa_overall_1`]. The dates are days since 1970-01-01: day of year = value −
   (days from 1970-01-01 to 1 January of the year) + 1; rate = EVI_Amplitude / (Maturity − Greenup)
   (`scripts/analisis_c14.py`).
3. Snow trends, whole pasture and per band [`smod_all`, `smod_b1800`, `smod_b2200`, `smod_b2600`; the same for `scd_*`
   with `"variable": "SCD", "metric": "days"`]:
   ```json
   {"tool": "trend_table", "args": {"region": R, "variable": "SMOD", "sensor": "Modis", "start": "2001-01-01",
    "end": "2025-12-31", "step": "annual", "metric": "melt", "stat": "median", "test": "hamed-rao", "where": W}}
   ```
   `trend_table` does not write the yearly values: get them with `time_series` and the same arguments (without
   `test`) [`smod_ts_all`, `scd_ts_all`].
4. Summer heat [`lst_all`, `lst_b1800`, `lst_b2200`, `lst_b2600`, `lst_ts_all`]:
   ```json
   {"tool": "trend_table", "args": {"region": R, "variable": "LST", "sensor": "Modis", "collection": "MODIS/061/MOD11A1",
    "start": "2001-01-01", "end": "2025-12-31", "step": "annual", "season": ["07-01", "08-31"], "metric": "mean",
    "stat": "median", "test": "hamed-rao", "where": W}}
   ```
5. Greenness [`ndvi16_2001_2012`, `ndvi16_2013_2025`, `ndvi_compare`, `ndvi_anom_spring`]: `time_series` of NDVI
   (MOD13Q1) `"step": "16-day"` in two halves; `compare_series` 2001-2012 vs 2013-2024 with `"step": "16-day"`; and the
   July indicator:
   ```json
   {"tool": "anomalies", "args": {"region": R, "variable": "NDVI", "sensor": "Modis", "collection": "MODIS/061/MOD13Q1",
    "start": "2001-01-01", "end": "2025-07-31", "step": "annual", "season": ["04-01", "07-15"], "metric": "mean",
    "stat": "median", "reference": ["2001-01-01", "2020-12-31"], "where": W}}
   ```
6. Local analysis (`scripts/analisis_c14.py`): yearly table per park, Kendall/Sen trends of the derived metrics,
   Spearman correlations between years, z of 2001-2020 (July indicator), LST trend with and without 2025.
7. Recruitment (`scripts/reclutamiento_sierra_nevada.py`): kids per female per year from the Darwin Core archive of
   GBIF (`https://ipt.gbif.es/archive.do?r=iberianibex`, CC0: `occurrence.txt`, `lifeStage == "kid"` over
   `sex == "female"`, years with ≥ 50 females), and Spearman against the satellite metrics of the same year; a
   sensitivity with only the years surveyed in September-December.

Total: 28 calls, each 11-70 s.

## Results to expect
Files under `<everest>/resultados/casos/C14/`.
- Mean green-up start (MCD12Q2 Greenup, day of year, 2001-2024): Sierra Nevada 93, Picos 120, Ordesa 123,
  Aigüestortes 142; mean melt-out (SMOD): 117, 132, 151, 150 (`tablas/anual_por_parque.csv`).
- Spearman SMOD ~ Greenup: 0.90 Aigüestortes, 0.64 Ordesa, 0.64 Picos, 0.55 Sierra Nevada (`tablas/correlaciones.csv`).
- SCD trend (Hamed-Rao, days/year): −2.83 Sierra Nevada (p 0.004), −1.64 Picos (p 0.032), −1.16 Aigüestortes
  (p 0.09), −0.77 Ordesa (p 0.30) (`llamadas/scd_all.json`).
- SMOD trend: −1.15 days/year in Picos (p 0.045); not significant elsewhere or in any band (`llamadas/smod_*.json`).
- July-August LST: +0.078 °C/year Picos 2200-2600 m (p 0.017), +0.087 Ordesa ≥ 2600 m (p 0.024) (`llamadas/lst_*.json`);
  2001-2021, whole pasture, +0.054 to +0.067 °C/year, not significant (simple Kendall, `tablas/anual_por_parque.csv`).
- Spring NDVI z ≤ −1: Sierra Nevada 2001, 2005, 2012, 2022; Aigüestortes 2013 (z −3.0) (`tablas/indicador_julio.csv`).
- Ibex kids per female 2001-2018 (n = 16): 0.13-0.45, no significant correlation with any satellite metric
  (`tablas/reclutamiento_correlaciones.csv`).

## Pitfalls
- MCD12Q2 dates are days since 1970, not days of the year; its green-up in high mountains largely follows the snow
  melt-out (check `QA_Overall_1`: worse in the Pyrenees, 0.3-0.4 on average, than in Sierra Nevada, 0.09).
- The MOD11A1 (Terra) LST of 2025 is 0.7-3.3 °C below 2024 in the four parks at once because the Terra overpass drifts
  earlier (MOD11A1 `Day_view_time`: ~11.0 h local solar time in 2001-2021, ~9.8 h in 2025; the drift starts in 2022;
  checked in the review of 2026-11-28, `resultados/casos/C14/revision/`). Check `Day_view_time`, end LST trends in
  2021 or move to a sensor with a stable overpass. Before MonitorEO 0.3.99, MODIS LST was sampled at 1 km on a UTM grid
  and had no snow filter.
- `trend_table` gives only the trend, not the yearly values: add the `time_series`.
- Picos has no treeless pixels ≥ 2600 m: that band returns n = 0.
- SCD is per calendar year (it includes the next autumn snow); a hydrological year would suit winter severity better.
- The 16-day NDVI metrics (peak date, 50 % crossing) are noisy because the snow filter changes the valid pixels from
  one step to the next; prefer MCD12Q2 or wait for per-pixel phenology metrics (M01).
- Open ibex censuses were made in different months (July to December) and with different effort each year, with no
  mange or body mass; no open chamois census series was found.

## Sources and citations
Pettorelli et al. 2005 (https://doi.org/10.1016/j.tree.2005.05.011), Pettorelli et al. 2007
(https://doi.org/10.1890/06-0875), Pettorelli et al. 2011 (https://doi.org/10.3354/cr00936), Rughetti &
Festa-Bianchet 2012 (https://doi.org/10.1644/11-MAMM-A-402.1), «Distinguishing disease effects from environmental effects in a mountain ungulate» (2015, Iberian ibex with
sarcoptic mange; https://doi.org/10.7589/2014-01-008), Büntgen et al. 2017 (https://doi.org/10.1002/ecs2.1761), Zhang et al. 2003
(https://doi.org/10.1016/S0034-4257(02)00135-9), Hall et al. 2002 (https://doi.org/10.1016/S0034-4257(02)00095-0),
Granados et al. 2020 (https://doi.org/10.1038/s41597-020-0544-1); all verified with scite on 2026-11-28. Census data:
doi:10.15470/3ucqfm (CC0). Cite MonitorEO (https://doi.org/10.5281/zenodo.23814894), Google Earth Engine
(https://doi.org/10.1016/j.rse.2017.06.031) and the references and credits that each result returns (all of them in
`tablas/referencias_monitoreo.json`).

## Files
`<everest>/resultados/casos/C14/`: `informe.md`, `estado.json`, `llamadas.json`,
`llamadas/`, `monitoreo/`, `tablas/`, `scripts/`, `fuentes/` (with `ORIGEN.txt`). Not published in the viewer.
