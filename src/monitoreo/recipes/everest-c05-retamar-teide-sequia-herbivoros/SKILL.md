---
name: everest-c05-retamar-teide-sequia-herbivoros
description: Decline of the summit broom shrubland (Spartocytisus supranubius) of Teide National Park (Tenerife) under drought and introduced herbivores (rabbit, mouflon). MSAVI2 of Landsat 8/9 (spring, 2013-2025) and Sentinel-2 (monthly, 2017-2026) over the MFE50 shrubland of Las Cañadas at 2,000-2,700 m without the 2023 burn, image counts, z anomalies, Mann-Kendall/Sen trends per region and per pixel, interannual CV by elevation band, and correlation with SPEI3/SPEI12, TerraClimate CWD and ERA5-Land precipitation (with and without trend). The fence/control BACI is prepared but pending the fence polygons. Use it to repeat this case or to adapt it to drought vs herbivory in sparse shrubland on dark volcanic soil.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  park: Teide National Park
  wdpa_id: "389013"
  event: "C05"
  event_date: "2013-2026 (drought 2024-2025; fences 2023-2026)"
  disturbance: drought
  status: partial
  monitoreo_version: "0.3.96"
---

# Teide broom shrubland: drought, herbivores and fences, 2013-2026

> **Files of this recipe.** `<everest>` is the folder of the EVEREST project where this case was computed: its
> zones (`resultados/casos/C05/*.gpkg`), its local scripts (`resultados/casos/C05/scripts/`) and its state files are
> not part of MonitorEO. To repeat the case, rebuild the shrubland zone from the MFE50 (or a better broom map) and run
> the calls below. See `monitoreo-disturbance-case-study` for the method.

## Question
Do fenced areas, or areas with rabbit and mouflon control, keep more greenness, cover and stability than open broom
shrubland, and how much of the decline is due to drought? It informs where to fence, where to concentrate control
hunting and, if drought dominates, where the refuges are and how to plan reinforcement planting. This run answers the
drought part. The fence part waits for the fence polygons and closing dates.

## Region and periods
- Shrubland: polygons `DEFINICION == "Matorral"` of the Mapa Forestal de España 1:50,000, province 38 (MITECO,
  `MFE50_38_tcm30-200077.zip`) inside the box UTM 28N 330-352 km E, 3,115-3,133 km N, minus the envelope of the 2023
  fire (`<everest>/resultados/teide/envolvente_incendio2023_s2.gpkg`, buffered 60 m). That gives 14,937.9 ha
  (`scripts/zona_retamar.py` → `retamar_mfe50.gpkg`, field `region` = `retamar`).
- Region in every satellite call (the three `image_count` calls use only `"min": 2000`, and
  `rs_ndvi_s2_2018_2022_cota` has no `where`): `{"file": "<everest>/resultados/casos/C05/retamar_mfe50.gpkg", "name_field":
  "region", "within": {"wdpa_id": 389013}}`, with `where` `[{"variable": "ELEVATION", "sensor": "Copernicus", "min":
  2000, "max": 2700}]` (about 101,800 Landsat pixels).
- Periods: Landsat spring (`season` ["04-15", "06-30"], growth and flowering) 2013-2025 for trends (Landsat 8/9 only).
  Sentinel-2 monthly 2017-04 to 2026-10. Anomaly reference: 2013-2022 (Landsat) and 2017-04 to 2023-07 (Sentinel-2).
  Stability: 2017-04 to 2023-03, before the 2024 drought.
- Sensors and why: MSAVI2 (soil-adjusted; NDVI of the shrubland is only 0.12-0.14). Landsat for 30 m trends.
  Sentinel-2 for monthly anomalies. Landsat 5/7 have no spring images over Tenerife in most years before 2013, so
  pre-2013 values are not used for trends. Climate: SPEIbase (55 km; check that it is not sea: 2 pixels over the
  park), TerraClimate (4.6 km), ERA5-Land (11 km).

## Steps
All calls are in `<everest>/resultados/casos/C05/llamadas.json` and were run with `herramientas/mcp_calls.py casos/C05`.
`R` = the region above and `W` = the elevation `where`.

1. Images: `image_count` MSAVI2 Landsat 1985-2025 `"step": "annual"`, `"season": ["04-15","06-30"]`, `"scale": 60`
   (`ic_msavi2_landsat_primavera`); the same for the full year 1985-2012 (`ic_msavi2_landsat_anual`); Sentinel-2
   2017-04-01/2026-10-31 monthly (`ic_msavi2_s2_mensual`).
2. Greenness of the shrubland by elevation: `region_stats` NDVI Sentinel-2 2018-2022 `"metric": "mean"`, `"scale": 20`,
   `"zones": {"variable": "ELEVATION", "sensor": "Copernicus", "breaks": [2000, 2200, 2400, 2600, 2800]}`
   (`rs_ndvi_s2_2018_2022_cota`).
3. Series:
   ```json
   {"tool": "time_series", "args": {"region": R, "variable": "MSAVI2", "sensor": "Landsat", "start": "1994-01-01",
    "end": "2025-12-31", "step": "annual", "season": ["04-15", "06-30"], "quality": {"harmonize": true}, "scale": 30,
    "where": W}}
   ```
   and MSAVI2 and NDVI of Sentinel-2, `"step": "monthly"`, `"scale": 20`, 2017-04-01/2026-10-31.
4. Anomalies: `anomalies` MSAVI2 Sentinel-2 monthly, `"reference": ["2017-04-01", "2023-07-31"]`, `"threshold": 1.5`
   (`an_msavi2_s2_mensual`), and Landsat spring annual 2013-2025 with reference 2013-2022 (`an_msavi2_landsat_primavera`).
5. Trends 2013-2025, Landsat spring: `trend_table` with `"test": "hamed-rao"`; `area_by_class` with `"trend": true`;
   `trend_map` with `"output": "slope"`.
6. Stability: `region_stats` NDVI and MSAVI2 Sentinel-2 2017-04-01/2023-03-31, `"temporal": "annual"`,
   `"interannual": "cv"`, `"zones"` of elevation [2000, 2200, 2400, 2600].
7. Climate: `time_series` SPEI12 and SPEI3 (`"sensor": "SPEIbase"`, `{"wdpa_id": 389013}`, monthly 1990-2024). CWD and
   PRECIP of TerraClimate (annual `"metric": "sum"`, 1990-2024) and PRECIP of ERA5-Land (1990-2025) over R.
8. Drought vs greenness (outside MonitorEO): `scripts/sequia_vs_verdor.py` → `sequia_vs_verdor.json`. It gives Pearson
   and Spearman correlations of the spring MSAVI2 with the climate of the same and the previous year, with and without
   linear trend, and of the monthly Sentinel-2 z with SPEI at lags of 0-6 months.
9. Pending, the fence BACI, once the polygons exist, one fence per call (or several with `pairs`):
   ```json
   {"tool": "control_ring", "args": {"region": {"file": "<fence_i.gpkg>"}, "gap": 30, "width": 300,
    "match": ["ELEVATION"], "within": {"wdpa_id": 389013}}}
   {"tool": "recovery_metrics", "args": {"region": {"file": "<fence_i_zones.gpkg>", "name_field": "region"},
    "affected": "afectada", "control": "control", "variable": "MSAVI2", "sensor": "Sentinel-2",
    "start": "2017-04-01", "end": "<today>", "event": "<closing date>", "step": "monthly", "reference_years": 3}}
   ```
   Add `region_stats` with `"interannual": "cv"` inside and outside each fence. For the control campaigns, run
   `time_series` with `"ring": true` over the hunting zones and compare the difference with the campaign dates.

## Results to expect
- MSAVI2 Landsat spring: mean 0.0826 in 2013-2016 and 0.0669 in 2024-2025 (`sequia_vs_verdor.json`). Trend 2013-2025:
  Sen −0.00119/yr, τ −0.59, p 0.005 (`llamadas/tt_msavi2_landsat_2013_2025.json`). The trend leans on the dry
  2024-2025 end: without those years it is not significant (see Pitfalls).
- Pixels: significant decrease 4,063.8 ha (47.0 %), no trend 4,462.7 ha (51.6 %), increase 120.2 ha (1.4 %)
  (`llamadas/abc_tendencia_msavi2_landsat_2013_2025.json`).
- Sentinel-2 MSAVI2 anomalies: negative episodes 2024-05/08 (peak −5.12), 2024-10/2025-01 and 2025-03/2026-01
  (11 months). Back to the reference in 2026 (`llamadas/an_msavi2_s2_mensual.json`). Landsat spring z: 2024 −1.84,
  2025 −1.91.
- Climate: 2024 CWD 1,488 mm, the highest since 1990 (1991-2020: 1,259 ± 98 mm). ERA5-Land precipitation 188 mm
  (302 ± 90). SPEI12 of December 2024: −2.62.
- Correlations (`sequia_vs_verdor.json`): spring MSAVI2 vs May SPEI12, r 0.69 (p 0.013), detrended 0.27 (p 0.40). Vs
  CWD of the year, r −0.66 (p 0.021). Vs previous-year ERA5-Land precipitation, r 0.65, detrended 0.56 (p 0.046).
  Monthly z vs SPEI3 lagged 3 months: r 0.42.
- Interannual CV of MSAVI2 (pixel mean): 7.0 % (2,000-2,200 m), 7.4 %, 10.2 %, 10.3 % (> 2,600 m)
  (`llamadas/rs_cv_msavi2_s2_cota.json`).

## Pitfalls
- No public fence polygons or closing dates. The large fences are from 2023-2026 (too recent), and the 400 m²
  exclosures are about 4 Sentinel-2 pixels. Do not trace fences from place names for a BACI.
- The MFE50 "Matorral" mixes broom with *Adenocarpus* and *Pterocephalus* (which is expanding). Replace it with a broom
  map when available.
- Landsat 5/7 gaps over Tenerife before 2013: check `image_count` and keep trends to Landsat 8/9.
- Shared trends in climate and greenness inflate correlations: detrend. But a weak detrended correlation does not
  show that the trend is not climatic (SPEI12 also declines).
- End-point effect: the 2013-2025 trend includes the 2024-2025 drought; with 2013-2023 the Sen slope of the annual
  means is −0.00092/yr, plain Mann-Kendall p 0.087 (reviewer's check on the time_series CSV, 2026-11-28).
- November has a tiny reference standard deviation, so its z values (−10 to −12) are inflated.
- The percentiles of the CV in `region_stats` came out identical within zones: use the mean.
- Exclude the 2023 burn (otherwise fire dominates the trend). Winter snow reduces valid pixels (February 2018).

## Sources and citations
- Fences (no geometry): Diario de Avisos, 18/01/2023, https://diariodeavisos.elespanol.com/2023/01/retamas-del-teide/ ;
  Gobierno de Canarias, 26/06/2026,
  https://www3.gobiernodecanarias.org/noticias/transicion-impulsa-la-recuperacion-del-retamar-de-cumbre-del-teide-con-una-inversion-superior-a-12-millones/
- MFE50: https://www.miteco.gob.es/es/biodiversidad/servicios/banco-datos-naturaleza/informacion-disponible/mfe50_descargas_canarias.html
- Literature (DOIs verified with scite): Cubas et al. (2018), doi:10.1007/s10530-017-1576-0; Olano et al. (2017),
  doi:10.1016/j.biocon.2017.09.008; Ibarrola-Ulzurrun et al. (2019), doi:10.1002/ecs2.2708; Irl et al. (2012),
  doi:10.1111/j.1654-1103.2012.01425.x; Marcos et al. (2023), doi:10.1016/j.rse.2022.113441; Qi et al. (1994),
  doi:10.1016/0034-4257(94)90134-1; Vicente-Serrano et al. (2010), doi:10.1175/2009JCLI2909.1; Abatzoglou et al.
  (2018), doi:10.1038/sdata.2017.191; Hamed & Rao (1998), doi:10.1016/S0022-1694(97)00125-X.
- Cite MonitorEO (doi:10.5281/zenodo.23814894), Google Earth Engine (Gorelick et al. 2017,
  doi:10.1016/j.rse.2017.06.031) and the references and credits that each result returns (in `llamadas/<id>.json`).

## Files
Under `<everest>/resultados/casos/C05/`: `informe.md`, `estado.json`, `llamadas.json`
(20 calls), `llamadas/`, `monitoreo/` (CSV, PNG, README), `retamar_mfe50.gpkg`, `scripts/zona_retamar.py`,
`scripts/sequia_vs_verdor.py`, `sequia_vs_verdor.json`, `fuentes/` (MFE50 and `ORIGEN.txt`). Not published in the
viewer.
