---
name: everest-aiguestortes-dieback-2012
description: Slow dieback and mortality of mountain pine (Pinus uncinata) under drought and bark beetles in Aigüestortes i Estany de Sant Maurici National Park (pressure, no official perimeter; validated for the sunny slope of Sant Maurici). Summer (July–September) Landsat and Sentinel-2 NDVI, LSWI, LST, albedo and CLre of an affected zone drawn from place names in the park reports against an elevation-matched control, BACI difference trends (Mann-Kendall and Sen) by sensor period, per-pixel trends with area_by_class, z anomalies and Marcos et al. (2023) pulse metrics (2017, 2022). Use it to repeat this case or to adapt it to a gradual forest decline without a perimeter or a date.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  park: Parc Nacional d'Aigüestortes i Estany de Sant Maurici
  wdpa_id: "196014"
  event: "aiguestortes_decaimiento_2012"
  event_date: "pressure without a start date; reference 1985-2011, stress pulses 2012, 2017 and 2022"
  disturbance: other  # dieback: drought and heat stress with bark beetles (Ips spp.), Armillaria
  status: validated
  monitoreo_version: "0.3.86"
---

# Mountain pine dieback, Aigüestortes (Espot sector), 2012–2026

> **Files of this recipe.** `<everest>` is the folder of the EVEREST project where this case was computed: its
> zones (`resultados/<park>/*.gpkg`), its local scripts (`herramientas/`, `scripts/`) and its state files are not part of
> MonitorEO. To repeat the case, rebuild them with MonitorEO: the affected area from the official perimeter
> (`{"ems": ...}`, `{"effis_id": ...}`, `{"wfs": ...}`) or from `burn_severity` with `perimeter: true`, the control
> with `control_ring` (or `ring: true`), and the series and metrics with the calls marked «now». See
> `monitoreo-disturbance-case-study` for the method.

## Question
Is the pine mortality that the park reports describe (Espot sector, 2012; worse in 2017 on the sunny slopes of Sant
Maurici and Peguera) visible from space, where, since when, and is the forest recovering? It informs where to focus
phytosanitary monitoring and whether the decline is a slow drift or discrete pulses (estado/parques/aiguestortes.json).

## Region and periods
- Affected area: no official perimeter. Zones were drawn **locally** with
  `resultados/aiguestortes/zonas_construccion/zonas_aig.py`: forest (ESA WorldCover 2021) within 500 m of the place
  names of the park reports (ICGC toponymy), 1600–2400 m, and on sunny slopes only aspect 90–270°. Result in
  `<everest>/resultados/aiguestortes/zonas.gpkg` (field `region`). The validated zone is
  `afectada_solana_sant_maurici` (218.2 ha, 1730–2290 m); `afectada` (677.5 ha, four sites) and `zonas_periferia.gpkg`
  (Cabanyeres, 361.4 ha, outside the WDPA) are complementary and not validated.
- Control: region `control` (373.4 ha): park forest 300 m–2.5 km from the affected zone, away from known avalanche paths,
  in its elevation band, with the share of sunny slope matched (60 % vs 62 %). Sensitivity: `control_anillo` (880.1 ha,
  same band, aspect not matched). MonitorEO has no tool for toponymy or aspect matching; «now» `control_ring` gives the
  ring version (step 2).
- where in every series: `[{"variable":"ELEVATION","sensor":"Copernicus","min":1783,"max":2248},{"landcover":"WorldCover","year":2021,"exclude":["water","grassland","wetland","cropland","shrubland","built","bare","snow"]}]`
  (below: **W**; p5–p95 of the affected zone from `region_stats`; 1633–2096 m for the periphery).
- Periods: reference 1985–2011 (Landsat 5/7) and 2013–2026 (Landsat 8/9) analysed separately; summer = July–September
  (snow and shadow the rest of the year); Sentinel-2 2017-03-28–2026 with July–August only (step 6, pitfalls).
- Sensors: Landsat for the long series; Sentinel-2 (CLre, red edge) for 2017–2026; MODIS not used (pixels too coarse for
  stands of a few hectares). No `harmonize`: the case interprets only the affected − control difference and
  same-sensor periods.

## Steps
All calls ran with `herramientas/mcp_calls.py aiguestortes resultados/aiguestortes/llamadas.json` (44 calls). Region
used by the zone calls (**R**): `{"file": "<everest>/resultados/aiguestortes/zonas.gpkg", "name_field": "region", "within": {"wdpa_id": 196014}}`.

0. «now», not run in this case: check summer images before choosing periods (Landsat 5 summers are sparse):
   `{"tool": "image_count", "args": {"region": R, "variable": "NDVI", "sensor": "Landsat", "start": "1985-01-01", "end": "2026-09-30", "step": "annual", "season": ["07-01", "09-30"]}}`
1. Inputs for the local zoning (DEM and land cover):
   `{"tool": "download_image", "args": {"region": {"bbox": [0.88, 42.53, 1.09, 42.63]}, "image": "ESA/WorldCover/v200", "band": "Map", "unit": "1", "resolution": 10}}`
   and `{"tool": "download_image", "args": {"region": {"bbox": [0.85, 42.5, 1.12, 42.65]}, "variable": "ELEVATION", "sensor": "Copernicus", "resolution": 30}}`
   (also the park DEM with `{"wdpa_id": 196014}`). Then `zonas_aig.py` (local, geopandas/rasterio).
2. Elevation band and aspect of the zones:
   `{"tool": "region_stats", "args": {"region": R, "variable": "ELEVATION", "sensor": "Copernicus"}}` and
   `{"tool": "region_stats", "args": {"region": R, "image": "COPERNICUS/DEM/GLO30", "band": "DEM", "terrain": "aspect", "stats": ["mean", "p5", "p50", "p95"]}}`.
   «now» for a ring control matched by elevation (the sensitivity control), with the slope polygon saved alone as
   `solana.gpkg` (field `region`):
   `{"tool": "control_ring", "args": {"region": {"file": "<everest>/resultados/aiguestortes/solana.gpkg", "name_field": "region"}, "gap": 300, "width": 2200, "within": {"wdpa_id": 196014}}}`
   then add the WorldCover condition of W, and for a sunny-slope-only control
   `{"variable": "ASPECT", "sensor": "Copernicus", "min": 90, "max": 270}`, to its `where`. Not run (solana.gpkg does
   not exist yet); the ASPECT condition replaces the aspect step of zonas_aig.py.
3. Monthly series June–October of each zone (Landsat 1985-01-01 → 2026-10-31; NDVI, LSWI, LST, ALBEDO):
   `{"tool": "time_series", "args": {"region": R, "variable": "NDVI", "sensor": "Landsat", "start": "1985-01-01", "end": "2026-10-31", "step": "monthly", "season": ["06-01", "10-31"], "where": W}}`
   and Sentinel-2 (NDVI, LSWI, CLre) with `"sensor": "Sentinel-2", "start": "2017-03-28"`.
4. Trends per period (summer, annual step): `trend_table` with W for 1985–2011 and 2013–2026 (NDVI, LSWI, LST; NDVI S2 2017–2026):
   `{"tool": "trend_table", "args": {"region": R, "variable": "NDVI", "sensor": "Landsat", "start": "2013-01-01", "end": "2026-09-30", "season": ["07-01", "09-30"], "step": "annual", "where": W}}`
5. Share of pixels with a significant trend (the «severity» of a pressure):
   `{"tool": "area_by_class", "args": {"region": R, "variable": "NDVI", "sensor": "Landsat", "trend": true, "start": "2013-01-01", "end": "2026-09-30", "season": ["07-01", "09-30"], "step": "annual", "where": W}}`
   repeated for 1985–2011, LSWI 2013–2026, Sentinel-2 2017–2026, and July–August only (`"season": ["07-01", "08-31"]`).
   Park-wide map: `download_trend` and `area_by_class` with `{"wdpa_id": 196014}` and ELEVATION 1600–2400 m.
6. Seasonal curve and Sentinel-2 checks: `compare_series` monthly 1985–2011 vs 2013-01-01–2026-10-31 (NDVI, LSWI);
   annual summer 2019–2021 vs 2023 and vs 2025–2026 (Sentinel-2); `compare_map` NDVI S2 2019-07-01/2021-09-30 vs
   2023-07-01/09-30 over the park (`"vmin": -0.15, "vmax": 0.15`).
7. Summer means and BACI trends/z: **local** scripts `verano_anual.py` (July–September mean per year, only months where
   affected and control both have ≥ 50 % valid pixels) and `analisis_presion.py` (difference affected − control,
   Mann-Kendall/Sen per period, z against 1985–2011). Outputs `subzonas/presion_<VAR>_<sensor>_solana_sant_maurici.json`.
8. Pulse metrics: **local** `herramientas/metricas_recuperacion.py` on the annual summer CSV (`metricas_lote.sh`;
   events 2003-07-01, 2013-01-01 for 2012, 2017-07-01, 2022-07-01; 3 reference years). «now», the same in MonitorEO
   (close, not identical: coverage is checked per region and step, and the summer value is the mean of the season):
   `{"tool": "recovery_metrics", "args": {"region": {"file": "<everest>/resultados/aiguestortes/zonas.gpkg", "name_field": "region", "within": {"wdpa_id": 196014}}, "affected": "afectada_solana_sant_maurici", "control": "control", "variable": "LSWI", "sensor": "Landsat", "start": "1985-01-01", "end": "2026-09-30", "event": "2017-07-01", "step": "annual", "season": ["07-01", "09-30"], "reference_years": 3, "min_coverage": 0.5, "where": W}}`
9. «now», optional: where the slope is losing, pixel by pixel (218 ha is small enough):
   `{"tool": "recovery_map", "args": {"region": {"file": "<everest>/resultados/aiguestortes/solana.gpkg", "name_field": "region"}, "variable": "NDVI", "sensor": "Landsat", "start": "2013-01-01", "end": "2026-09-30", "event": "2017-07-01", "season": ["07-01", "09-30"], "resolution": 30, "where": W}}`

## Results to expect
From estado/parques/aiguestortes.json (`analisis.resumen`, `analisis.metricas`, «Caso cerrado» section) and
`resultados/aiguestortes/subzonas/presion_*_solana_sant_maurici.json`, `subzonas/metricas_*_sant_maurici.json`:
- Summer NDVI advantage of the Sant Maurici slope over the control: 0.0700 (1985–2011) → 0.0426 (2013–2026), −39.1 %;
  LSWI −30.5 % (0.0564 → 0.0392).
- Sen slope of the difference per decade: NDVI −0.0079 (p = 0.0040) 1985–2011, −0.0157 (p = 0.0010) 2013–2026,
  −0.0118 (p < 0.0001) 1985–2026; LSWI −0.0281 (p = 0.0001) 2013–2026; LST −0.0436 (p = 0.375) and albedo 0.0005
  (p = 0.238) 1985–2026: no energy signal. Ring control: NDVI −0.0120, LSWI −0.0310 in 2013–2026 (same result).
- Per pixel 2013–2026 (area_by_class): 12.3 % of the slope (20.0 ha) with significant NDVI decrease vs 4.0 % in the
  control (excess ≈ 13.5 ha); July–August 11.0 % vs 1.9 %; LSWI 13.0 % vs 2.7 %.
- z of the summer difference < −2: NDVI 2018, 2019, 2020, 2022–2026; LSWI 2020, 2022–2026 (minimum −2.76).
- Pulse 2017 (difference, Landsat summer): NDVI −6.43 MAD, DIT 2 years, no RRT; LSWI −5.44 MAD, DIT 1, RET 8 years.
  Pulse 2022: LSWI difference −1.27 MAD, RET 3 years. Provisional (last pulse < 5 years old).
- Sentinel-2 2017–2026 (July–August) does not confirm a trend on the slope: NDVI −0.0109/decade (p = 0.371),
  LSWI −0.0163 (p = 0.107).

## Pitfalls
- No perimeter and no date: zone placed by toponymy (500 m radius), not by the park's monitoring plots; the zone
  contains healthy pine and the control may contain affected trees. The zone was not drawn from the trend, to avoid
  circularity: the trend was measured afterwards inside it.
- Landsat gap 2012-05-05 → 2013-03-18 hides the 2012 pulse; the TM/ETM+ → OLI change inflates long trends (99.5 % of
  park forest «greening» in 1985–2026): read only the difference and the same-sensor periods.
- Monthly series are 61 % interpolated (snow November–May) and gave unrealistic STL impacts; use the annual summer series.
- September 2024 in Sentinel-2 is anomalous in every zone (early snow or shadow): Sentinel-2 analysed with July–August.
- `area_by_class` with trend over 1985–2026 in the zones failed with «User memory limit exceeded»: split into 1985–2011
  and 2013–2026.
- The decline is a slow drift: DIT/RRT/RET say little; rank dimensions by the difference trend and the persistence of z.
- The drop comes one or two summers after the pulse (needle loss after beetle attack): not within ±3 months.

## Sources and citations
- Park reports (OAPN/MITECO): 2012 https://www.miteco.gob.es/content/dam/miteco/es/parques-nacionales-oapn/red-parques-nacionales/parques-nacionales/Memoria_2012ESP_tcm30-59514.pdf ;
  2017 https://www.miteco.gob.es/content/dam/miteco/es/parques-nacionales-oapn/red-parques-nacionales/parques-nacionales/memoria-aigues-2017-cast_tcm30-503773.pdf ;
  2014 and 2016 in `eventos[].fuentes`; 2020, 2023, 2024 as local PDFs in `resultados/aiguestortes/fuentes/` (no URL recorded).
- Method: Marcos et al. 2023, doi:10.1016/j.rse.2022.113441; Roy et al. 2016 (Landsat 7→8 NDVI continuity),
  doi:10.1016/j.rse.2015.12.024; Buras et al. 2021, doi:10.3389/fpls.2021.689220; Moreno-Fernández et al. 2021,
  doi:10.1016/j.scitotenv.2021.148578; Vogelmann et al. 2009, doi:10.1016/j.rse.2009.04.014; Assal et al. 2016,
  doi:10.1016/j.foreco.2016.01.017.
- Ecology: Gazol et al. 2018, doi:10.1111/gcb.14082 and doi:10.3389/fpls.2018.01546; Anderegg et al. 2015,
  doi:10.1126/science.aab1833; Galván et al. 2015, doi:10.1016/j.gloplacha.2014.11.011; Rull et al. 2024,
  doi:10.3390/plants13081144; Gharun et al. 2024, doi:10.5194/bg-21-5481-2024 (all verified in the park json).
- Cite MonitorEO (doi:10.5281/zenodo.23814894), Google Earth Engine (Gorelick et al. 2017, doi:10.1016/j.rse.2017.06.031)
  and the references and credits that each result returns (`resultados/aiguestortes/referencias_monitoreo.json`).

## Files
- `<everest>/resultados/aiguestortes/`: `llamadas.json`, `llamadas/`, `monitoreo/` (CSV,
  PNG, README), `zonas.gpkg`, `zonas_periferia.gpkg`, `zonas_construccion/`, `*_verano_anual.csv`, `presion_*.json`,
  `subzonas/` (validated slope), `figura_baci_NDVI_LSWI.png`, `figura_tendencia_NDVI_2013_2026.png`.
- State and text: `estado/parques/aiguestortes.json`; report `informe_perturbaciones.html`. Not published in the
  results viewer (not recorded).
- Pending (from the json): plot coordinates and Ips traps from the park, ICGC orthophotos, DeBosCat polygons and the
  Senf & Seidl (2021) map for an independent check.
