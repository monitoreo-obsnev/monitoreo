---
name: everest-c17-nieve-polvo-careo-sierra-nevada
description: Snow duration, melt-out day and snow albedo since 2000 in four headwater catchments of Sierra Nevada National Park (Poqueira, Trevelez, Berchules, Alhori), whether Saharan dust advances the melt, and what it means for the careo (recharge) channels, with Guadarrama as contrast. Catchments traced from MERIT Hydro D8, MODIS SCD, SCF and SMOD (Terra, checked with Aqua and Sentinel-2) with Hamed-Rao Mann-Kendall and Sen trends by elevation and by month, z anomalies, MOD10A1 snow albedo, MAIAC and CAMS aerosol and dust AOD, ERA5-Land climate, MOD16 ET and TerraClimate soil moisture, and a local regression and dust-episode analysis. Use it to repeat this case or to adapt it to the snowpack trends and dust-on-snow question of any mountain catchment. Partial results, without gauging data or a map of the careo channels, the recharge is not measured.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  park: Sierra Nevada National Park (contrast Sierra de Guadarrama National Park)
  wdpa_id: "389011"
  event: "C17"
  event_date: "2000-09-01/2025-08-31"
  disturbance: other
  status: partial
  monitoreo_version: "0.3.96"
---

# Snow, Saharan dust and careo recharge in the headwaters of Sierra Nevada, 2000-2025

> **Versions of MonitorEO.** Computed with MonitorEO 0.3.96, before 0.3.99. Since 0.3.99 a variable of MODIS of the
> catalog is reduced, at its resolution, on the sinusoidal grid of its products (not on pixels of 250-1000 m of the
> UTM zone; data given by collection and band are not); the ALBEDO of MODIS (MCD43A3) keeps the magnitude inversions,
> so it has values over snow: a repetition gives slightly different MODIS values.

> **Files of this recipe.** `<everest>` is the folder of the EVEREST project where this case was computed: its catchments (`resultados/casos/C17/cuencas.gpkg`), its local scripts
> (`resultados/casos/C17/scripts/`) and its state files are not part of MonitorEO. To repeat the case, rebuild the
> catchments with `scripts/cuencas.py` (or use an official catchment layer) and run the calls below. See
> `monitoreo-disturbance-case-study` for the general method (trends, anomalies).

## Question
How have the snow cover duration (SCD), the melt-out day (SMOD) and the snow albedo changed since 2000 in the headwaters
of the Poqueira, Trevelez, Berchules and Alhori, does Saharan dust advance the melt, and what does it mean for the
recharge by the careo channels? It informs which careo channels to restore first and when to open them, and the
assessment of the water regulation service of the park.

## Region and periods
- Catchments: traced with `scripts/cuencas.py` from the D8 flow direction of MERIT Hydro v1.0.1 (Earth Engine
  `MERIT/Hydro/v1_0_1`, read with `sampleRectangle` over -3.45/36.90/-3.05/37.22) from approximate outlets
  (`scripts/desagues.json`: Poqueira -3.361 36.938, Trevelez -3.272 36.995, Berchules -3.191 36.975, Alhori -3.150
  37.190, snapped to the cell of largest upstream area within 6 cells). Areas: Poqueira 83.7 km², Trevelez 84.8 km²,
  Berchules 57.0 km², Alhori 55.1 km². Check: Veleta and Capileira in Poqueira, Mulhacen on the Poqueira-Trevelez
  divide, each village in its catchment, no overlaps. Not the official catchment map.
- Region in every catchment call: `{"file": "<everest>/resultados/casos/C17/cuencas.gpkg", "name_field": "cuenca",
  "within": {"wdpa_id": 389011}}` (only the part inside the National Park; median elevation 2,100-2,588 m).
  `where` for the high band: `[{"variable": "ELEVATION", "sensor": "Copernicus", "min": 2500}]`.
- Aerosols: region `{"wdpa_id": 389011}` (whole park). Contrast: `{"wdpa_id": 555546231}` with ELEVATION ≥ 1800.
- Periods: hydrological year `season: ["09-01","08-31"]` from 2000-09-01 to 2025-08-31 (labelled by the September
  year) for SCD and SCF; SMOD per calendar year 2001-2025 (default season 1 Jan-31 Aug); albedo March-June; aerosols
  February-June daily.
- Sensors and why: MODIS Terra (MOD10A1, daily 500 m) for the 25-year series; Aqua (MYD10A1) and Sentinel-2 (20 m, from
  2017) as checks; MOD10A1 `Snow_Albedo_Daily_Tile` for the albedo of the snow itself; MAIAC (MCD19A2) and CAMS NRT for
  aerosols (CAMS dust AOD only exists from late June 2021).

## Steps
All calls are in `<everest>/resultados/casos/C17/llamadas.json` (run with `herramientas/mcp_calls.py casos/C17 ...`).
`R` = the catchment region above; `HY` = `["09-01","08-31"]`; `HI` = the ELEVATION ≥ 2500 condition.

1. Elevation of the catchments: `region_stats` `{"region": R, "variable": "ELEVATION", "sensor": "Copernicus",
   "stats": ["mean","min","p5","p25","p50","p75","p95","max"]}`.
2. SCD and SMOD by elevation band: `region_stats` `{"region": R, "variable": "SCD", "sensor": "Modis", "start":
   "2000-09-01", "end": "2025-08-31", "metric": "days", "temporal": "annual", "season": HY, "zones": {"variable":
   "ELEVATION", "sensor": "Copernicus", "breaks": [2000, 2500, 3000]}}`; the same with `"variable": "SMOD", "metric":
   "melt", "start": "2001-01-01"` and no season.
3. Annual series and trends of SCD: `time_series` and `trend_table` `{"region": R, "variable": "SCD", "sensor": "Modis",
   "start": "2000-09-01", "end": "2025-08-31", "step": "annual", "metric": "days", "season": HY, "test": "hamed-rao"}`;
   again with `"where": HI`; again with `"collection": "MODIS/061/MYD10A1", "start": "2002-09-01"` (Aqua).
4. SMOD: `time_series` and `trend_table` `{"region": R, "variable": "SMOD", "sensor": "Modis", "start": "2001-01-01",
   "end": "2025-08-31", "step": "annual", "metric": "melt", "test": "hamed-rao"}`; with `where` HI; with the Aqua
   collection from 2003-01-01; `anomalies` with the same arguments and `"threshold": 1.5`.
5. SCF: `trend_table` `{"region": R, "variable": "SCF", "sensor": "Modis", "start": "2000-09-01", "end": "2025-08-31",
   "step": "annual", "metric": "mean", "season": HY, "test": "hamed-rao"}` and with `"step": "monthly"` (no season);
   daily SCF Feb-June 2016-2025 with `where` HI for the dust episodes.
6. Sentinel-2 check: `time_series` SCD (`"sensor": "Sentinel-2", "start": "2017-09-01", "scale": 20`) and SMOD
   (`"start": "2018-01-01", "scale": 20`).
7. Snow albedo: `time_series` `{"region": R, "collection": "MODIS/061/MOD10A1", "band": "Snow_Albedo_Daily_Tile",
   "band_scale": 0.01, "unit": "1", "start": "2001-03-01", "end": "2025-06-30", "step": "16-day", "season":
   ["03-01","06-30"], "metric": "median", "where": HI}`; `trend_table` of the same with `"step": "monthly"` and
   `"annual"` and `"test": "hamed-rao"`; daily, `"metric": "mean"`, Feb-June 2016-2025.
8. Aerosols over the park: `time_series` `{"region": {"wdpa_id": 389011}, "variable": "ARSL", "sensor": "Modis",
   "step": "daily", "season": ["02-01","06-30"], "metric": "mean"}` in two periods (2001-2012, 2013-2025-08-31; ~6 min
   each); CAMS `{"collection": "ECMWF/CAMS/NRT", "band": "dust_aerosol_optical_depth_at_550nm_surface", "unit": "1",
   "start": "2016-06-22", "end": "2025-08-31", "step": "daily", "season": ["02-01","06-30"], "scale": 5000}` and the
   same with `total_aerosol_optical_depth_at_550nm_surface`; dust also for Guadarrama.
9. Climate and balance per catchment: `time_series` PRECIP ERA5-Land (annual, `season` HY, `metric` sum), TMEAN
   ERA5-Land (annual, season March-June), ET Modis (annual sum 2001-2024), SOILM TerraClimate (monthly 2001-2024).
10. Guadarrama: `trend_table` SCD and SMOD as in 3-4 with `{"wdpa_id": 555546231}` and ELEVATION ≥ 1800.
11. Local analysis: `scripts/analisis.py` (with `PYTHONNOUSERSITE=1`): annual table, regressions SMOD ~ P + T + AOD,
    dust episodes (CAMS dust AOD ≥ 0.3) with snow albedo and SCF 7 days before and after, against dust-free windows.

## Results to expect
- SCD trends (Terra, Sen days/year; `llamadas/tt_scd_modis.json`): Poqueira -2.12 (p 0.006), Trevelez -2.02 (0.003),
  Berchules -2.33 (<0.001), Alhori -1.70 (0.005); ≥ 2500 m -1.93 to -3.14 (`tt_scd_modis_2500.json`); Aqua 2002-2024
  -1.79 to -3.05, all significant (`tt_scd_aqua.json`). Mean SCD 68.5-111.5 days (`analisis/resumen_analisis.json`).
- SCF declines significantly in December, January and February (-1.17 to -1.89 %/year), not in March-May
  (`tt_scf_mensual.json`).
- SMOD: no significant trend anywhere (Terra -0.12 to -0.51 days/year, Aqua -0.05 to -0.98; `tt_smod_*.json`);
  mean SMOD day 90.6-120.7; early melt anomalies in 2023 (Poqueira z -3.34) and 2021, late in 2003, 2004, 2018
  (`an_smod_modis.json`). Sentinel-2 SMOD 16-28 days earlier than MODIS.
- SMOD ~ P + T: R² 0.63 in Trevelez (spring temperature -8.9 days per SD, p 0.0007), 0.39 in Poqueira; spring AOD adds
  nothing (p 0.32-0.88 MAIAC; 0.14-0.87 CAMS 2017-2025).
- Dust: 10 episodes with CAMS dust AOD ≥ 0.3 (Feb-June 2022-2025), peaks 0.66 on 2022-03-15 and 2024-04-07; snow albedo
  change after - before: mean -0.032, median -0.055 (n 26) vs -0.023 / -0.038 in dust-free windows (n 79),
  Mann-Whitney p 0.51 (`analisis/episodios_polvo.csv`, `resumen_analisis.json`).
- Snow albedo trends March-June: none significant except June in Alhori (+0.0023/year, p 0.03).
- Guadarrama ≥ 1800 m: SCD -2.59 days/year (p < 0.001), SMOD +0.31 (p 0.67).

## Pitfalls
- In 0.3.96 `image_count` failed with snow variables (fixed in 0.3.99); the number of images was taken from
  `n_images` of the series.
- With MonitorEO 0.3.96, the catalog `ALBEDO` (MCD43A3) with its quality filter kept almost only snow-free pixels (since
  0.3.99 it keeps the magnitude inversions, with values over snow) (0.11-0.13 in spring), and
  without it many March days are missing: for the albedo of the snow use MOD10A1 `Snow_Albedo_Daily_Tile` (Earth
  Engine already masks the non-snow codes > 100).
- CAMS NRT `dust_aerosol_optical_depth_at_550nm_surface` only has data from late June 2021; the total AOD from 2016.
  MAIAC `ARSL` removes snow pixels, so in winter there are few valid pixels over the summits (the script keeps days with
  ≥ 20 pixels).
- Hydrological-year steps are labelled by the September year ("2000" = hydrological year 2000/01, September 2000 to August 2001); SMOD by the calendar year.
- Dust events often come with snowfall (March 2022): the fresh snow hides the dust and raises the albedo; and clouds
  hide the days right after the deposition.
- Daily ARSL over 12 years takes ~6 minutes; split the period.

## Sources and citations
Careo channels: https://doi.org/10.1016/j.scitotenv.2022.153937, https://doi.org/10.3390/w14193130,
https://doi.org/10.55407/geogaceta99830. Snow albedo and dust: https://doi.org/10.3390/atmos13111903,
https://doi.org/10.5194/tc-13-1147-2019, https://doi.org/10.1038/s41467-022-32501-y; Saharan dust in Iberia:
https://doi.org/10.1016/j.scitotenv.2020.137041, March 2022 event https://doi.org/10.1016/j.chemosphere.2025.144778.
Snowpacks: https://doi.org/10.1088/1748-9326/aa70cb, https://doi.org/10.5194/hess-19-2337-2015. MERIT Hydro:
https://doi.org/10.1029/2019WR024873. Trends: https://doi.org/10.1016/S0022-1694(97)00125-X,
https://doi.org/10.1080/01621459.1968.10480934 (all verified with scite, 2026-11-28). Cite MonitorEO
(https://doi.org/10.5281/zenodo.23814894), Google Earth Engine (https://doi.org/10.1016/j.rse.2017.06.031) and the
references and credits that each result returns (collected in `analisis/referencias_monitoreo.txt`).

## Files
`<everest>/resultados/casos/C17/`: `informe.md`, `estado.json`, `cuencas.gpkg`,
`llamadas.json`, `llamadas/` (responses), `monitoreo/` (CSV, PNG, README), `analisis/` (annual table, dust episodes,
summary, figure, references), `scripts/` (`cuencas.py`, `desagues.json`, `analisis.py`), `fuentes/ORIGEN.txt`.
Not published in the viewer.
