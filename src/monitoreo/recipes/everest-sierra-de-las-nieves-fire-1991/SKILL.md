---
name: everest-sierra-de-las-nieves-fire-1991
description: Rio Verde wildfire of 7 August 1991 in Sierra de las Nieves National Park (Malaga, Spain), 8,157 ha of pine forest and Mediterranean shrubland. Burn severity with Landsat 5 TM (dNBR and one-year RdNBR) over the official REDIAM perimeter, contrast with the satellite perimeter and with the European Forest Disturbance Atlas, and 35 years of recovery of NDVI, EVI, LSWI, LST and albedo of Landsat 5/7/8/9 (monthly) in the burned area against a cleaned control ring, with the metrics of Marcos et al. (2023), plus late-phase LAI and ET of MODIS. Use it to repeat this case or to adapt it to an old fire (pre-2000, Landsat 5 era, no EFFIS) with an official perimeter, where the pre-fire images are few and the control must exclude later disturbances.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  park: Sierra de las Nieves National Park
  wdpa_id: "555700945"
  event: "sierra_de_las_nieves_incendio_1991"
  event_date: "1991-08-07"
  disturbance: fire
  status: validated
  monitoreo_version: "0.3.86"
---

# Rio Verde fire, Sierra de las Nieves, 1991

> **Files of this recipe.** `<everest>` is the folder of the EVEREST project where this case was computed: its
> zones (`resultados/<park>/*.gpkg`), its local scripts (`herramientas/`, `scripts/`) and its state files are not part of
> MonitorEO. To repeat the case, rebuild them with MonitorEO: the affected area from the official perimeter
> (`{"ems": ...}`, `{"effis_id": ...}`, `{"wfs": ...}`) or from `burn_severity` with `perimeter: true`, the control
> with `control_ring` (or `ring: true`), and the series and metrics with the calls marked «now». See
> `monitoreo-disturbance-case-study` for the method.

## Question
How severe was the 1991 Rio Verde fire, the largest disturbance recorded in the park (34 % of its area), and has the
burned area recovered its function 35 years later, once the regional greening and the change of Landsat sensor are
removed with a control? It informs whether the scar needs restoration or only monitoring, and where (the area with a
significant NDVI decline since 2013).

## Region and periods
- Affected area: official REDIAM perimeter (WFS `REDIAM_WFS_area_recorrida_fuego`, layer `ms:Area_afectada_historico`,
  `fecha_inic` 19910807, Tolox, 8,156.7 ha, delineated with Landsat 5 TM), downloaded by hand (REDIAM's certificate
  cannot be verified, so `{"url": ...}` does not work) to `fuentes/rediam_area_afectada_historico_bbox.geojson` and
  saved as `perimetros/rediam_1991_rioverde.gpkg`. For the series, that perimeter minus what was disturbed later
  (EFDA last disturbance ≥ 1994, Hansen loss 2001-2025, EFFIS 2026-02-20, REDIAM reburns; 3.2 %):
  `perimetros/afectada_limpia.gpkg`, region `afectada`, 7,893.4 ha.
- Control: ring from 300 to 3,300 m around the affected area (`herramientas/zonas.py --separacion 300 --ancho 3000`),
  without the 1991 perimeter, the other REDIAM (1975-2021) and EFFIS (2017-2026) fires, all EFDA 1985-2023 disturbed
  pixels and Hansen loss 2001-2025, used only inside the park: region `control`, 9,347.3 ha (2,844 ha in the park).
  In `zonas.gpkg`. `where` in every series:
  `[{"variable": "ELEVATION", "sensor": "Copernicus", "min": 476, "max": 1276}, {"landcover": "CORINE", "year": 1990,
  "exclude": ["water", "built", "cropland", "bare", "grassland", "wetland", "snow"]}]`
  (p5-p95 of the affected elevation; pre-fire land cover). After `where`: 7,144.4 ha affected, 958.5 ha control.
- Periods: severity before 1991-05-07/08-06, after 1991-08-20/10-31 (dNBR) and 1992-06-01/08-31 (RdNBR, one year,
  same season); series 1984-03-16 to 2026-10-31; metrics with a 3-year reference (1988-09 to 1991-08).
- Sensors and why: Landsat 5 TM is the only sensor for the event; series with Landsat 5, 7, 8, 9 (gap 2012-05-05 to
  2013-03-18, interpolated) at `scale` 60; MODIS only for the late phase (2000-2026, no pre-fire reference).

## Steps
1. Images before the fire. Done as a monthly NDVI series over the REDIAM perimeter, reading `n_images`:
   `{"tool": "time_series", "args": {"region": {"file": "<everest>/resultados/sierra_de_las_nieves/perimetros/rediam_1991_rioverde.gpkg", "name_field": "region"}, "variable": "NDVI", "sensor": "Landsat", "start": "1984-03-01", "end": "1992-12-31", "step": "monthly", "scale": 60}}`
   **Now**: `{"tool": "image_count", "args": {"region": <same>, "variable": "NDVI", "sensor": "Landsat",
   "start": "1984-03-16", "end": "1992-12-31", "step": "monthly", "scale": 60}}`.
2. Burn severity, dNBR with perimeter over a wide box, then the park, then the official perimeter (with and without
   `"within": {"wdpa_id": 555700945}`):
   ```json
   {"tool": "burn_severity", "args": {"region": {"bbox": [-5.1, 36.55, -4.88, 36.71]}, "sensor": "Landsat",
    "start": "1991-05-07", "end": "1991-08-06", "other_start": "1991-08-20", "other_end": "1991-10-31",
    "perimeter": true}}
   ```
   Then `"region": {"wdpa_id": 555700945}` with `"perimeter": true`, and `"region": {"file": ".../perimetros/rediam_1991_rioverde.gpkg", "name_field": "region"}`
   (ids `bs_L5_dnbr_{bbox,parque,rediam,rediam_parque}`). RdNBR one year later: the same with `"index": "RdNBR",
   "start": "1991-06-01", "end": "1991-08-06", "other_start": "1992-06-01", "other_end": "1992-08-31"` (ids
   `bs_L5_rdnbr_1anio_*`). The satellite perimeter was kept as the patches touching REDIAM (GeoPandas, outside
   MonitorEO). **Now**: add `"largest": true` (or `"seed": [-4.9957, 36.6323]`, the approximate point of the event in the park's json;
   check that it falls inside the burned area) to keep only the fire's patch.
3. Zones and matching: `region_stats` of ELEVATION (`"stats": ["mean","min","p5","p25","p50","p75","p95","max"]`) over
   the perimeter in the park (p5/p95 → 476/1,276 m); `area_by_class` with `"landcover": "CORINE", "year": 1990` over
   `zonas.gpkg`; `region_stats` with `"image": "COPERNICUS/DEM/GLO30_2024_1", "band": "DEM", "terrain": "aspect"` (and
   `"slope"`) with the `where` to check the match. The ring was built with `herramientas/zonas.py`. **Now**:
   ```json
   {"tool": "control_ring", "args": {"region": {"file": "<everest>/resultados/sierra_de_las_nieves/perimetros/afectada_limpia.gpkg", "name_field": "region"},
    "gap": 300, "width": 3000, "exclude": {"file": "<one GeoPackage with all the exclusion polygons>"},
    "within": {"wdpa_id": 555700945}}}
   ```
   (`exclude` takes one region: merge `perimetros/efda_todo_1985_2023.gpkg`, `hansen_perdida_2001_2025.gpkg`,
   `effis_2017_2026.gpkg`, `rediam_otros_incendios.gpkg` first). Add the CORINE 1990 condition to its `where`.
4. Monthly series 1984-03-16 to 2026-10-31 of NDVI, LSWI, LST, ALBEDO, EVI, NBR (ids `ts_<VAR>_Landsat`):
   ```json
   {"tool": "time_series", "args": {"region": {"file": "<everest>/resultados/sierra_de_las_nieves/zonas.gpkg",
    "name_field": "region", "within": {"wdpa_id": 555700945}}, "variable": "NDVI", "sensor": "Landsat",
    "start": "1984-03-16", "end": "2026-10-31", "step": "monthly", "scale": 60, "where": <the where above>}}
   ```
   MODIS late phase: `"variable": "LAI"` and `"ET"`, `"sensor": "Modis"`, `"start": "2000-03-01"` (no `scale`).
   Months with < 50 % of the valid pixels were blanked locally (`filtrar_serie.py`, also `--sin-2023` for a
   sensitivity test). **Now**: `"min_coverage": 0.5` in `time_series` / `recovery_metrics`.
5. Seasonal curves: `compare_series` 1985-01-01/1991-07-31 vs 1992-01-01/1996-12-31 and vs 2016-01-01/2026-10-31,
   `"step": "monthly"`, for NDVI, LSWI, LST, ALBEDO (ids `cs_<VAR>_pre_vs_*`).
6. Trends: `trend_table` `"step": "annual"` 1985-01-01/1991-07-31 and 1992-01-01/2026-10-31 (ids `tt_<VAR>_*`).
   Per pixel: `area_by_class` with `"trend": true, "step": "annual"` for NDVI; 1992-2026 failed («User memory limit
   exceeded»), so it was split into 1992-01-01/2011-12-31 and 2013-04-01/2026-10-31.
7. Recovery metrics: `herramientas/metricas_recuperacion.py` on the filtered CSVs (`--evento 1991-08-07 --afectada
   afectada --control control`, 3 reference years). **Now**:
   ```json
   {"tool": "recovery_metrics", "args": {"region": {"file": "<everest>/resultados/sierra_de_las_nieves/zonas.gpkg",
    "name_field": "region", "within": {"wdpa_id": 555700945}}, "affected": "afectada", "control": "control",
    "variable": "NDVI", "sensor": "Landsat", "start": "1984-03-16", "end": "2026-10-31", "event": "1991-08-07",
    "step": "monthly", "scale": 60, "reference_years": 3, "min_coverage": 0.5, "where": <the where above>}}
   ```
   Repeat for EVI, LSWI, LST, ALBEDO. Consider `"quality": {"harmonize": true}` (series cross 2013).
8. (now, not run) `recovery_map` of NDVI over `afectada_limpia.gpkg`, `"season": ["06-01", "08-31"]`,
   `"resolution": 60`, `"event": "1991-08-07"`, to map where it is back to its reference.

## Results to expect
From `estado/parques/sierra_de_las_nieves.json` (`analisis`) and the files named:
- Landsat 5 before the fire: 163 scenes, 67 of 79 months with data, 52 with ≥ 50 % valid pixels; 22 of 36 valid
  months in the 3 reference years (`llamadas/n_imagenes_L5_1984_1992.json`). NDVI of the affected area 0.42 (1991-07)
  → 0.16 (1991-08).
- dNBR in the REDIAM perimeter: low 726.4, moderate-low 1,837.6, moderate-high 3,378.5, high 1,516.0 ha; burned
  (≥ 0.1) 7,458.5 ha; 444 ha without data. RdNBR: low 1,122.5, moderate 5,008.7, high 1,708.7 ha (median 0.49).
- Satellite dNBR perimeter 8,386.3 ha (+2.8 % vs 8,156.7 ha, IoU 0.86); RdNBR 8,560.2 ha (+4.9 %, IoU 0.90).
- EFDA v2.1.1: 1,821 ha of forest disturbed in 1992 inside the scar, 98.3 % fire agent; Spearman ρ = −0.52 with dNBR.
- NDVI (`metricas_NDVI_Landsat.json`): S95 0.211, −71.0 %, −24.83 MAD, DIT 0.32, RRT 10.98 years (2002-08);
  difference −35.22 MAD, no RRT, RET 13.24 years, 82.1 % recovered.
- Difference affected − control, impact in MAD / RET / % recovered: EVI −53.1 / 24.2 / 85; LSWI −43.2 / 5.3 / 87;
  LST +42.0 / 12.8 / 92; ALBEDO −12.1 / 9.4 / 150 (the only RRT of the difference: 20.0 years)
  (`metricas_<VAR>_Landsat.json`). Without 2023 (`*_sin2023.json`) times do not change.
- Per-pixel NDVI trend: 97.0 % of the affected area increasing in 1992-2011; 17.2 % increasing, 79.5 % no trend and
  3.4 % (230 ha) decreasing in 2013-2026.

## Pitfalls
- Few Landsat 5 images before 1991 and steep terrain: months with few valid pixels give spurious means; filter them
  (now `min_coverage`). Only 7 pre-fire years: no 8-year pre-trend.
- dNBR over the whole park gives 9,037 ha because summer drying passes 0.1 outside the fire: use the perimeter (now
  `seed`/`largest`).
- The control must exclude everything disturbed later (EFDA, Hansen, EFFIS, other REDIAM fires); the ring outside the
  park was not used because EFDA and Hansen were clipped to the park only. Later disturbances inside the scar cannot be
  masked by year: they were removed for the whole period.
- Regional greening and the Landsat 5/7 → 8/9 jump inflate long trends: interpret the difference affected − control.
  The LST difference peak in 2011-2013 is an interpolation artefact of the Landsat gap.
- The RET of the affected area alone (2.3 years for NDVI) is an artefact of the 5 % threshold during the slow rise.
- Date: 7 August (REDIAM) vs 8 August (EGU2015); area 8,156.7 ha (REDIAM) vs ~9,000 ha (Catalina Mimendi 2019).
- RdNBR classes were calibrated in Californian conifers: indicative only in Mediterranean shrubland.
- Warnings: Landsat 5 starts 1984-03-16 (asked from 1984-03-01); MCD15A3H LAI starts 2002-07-04 (asked from 2000-03-01).
  Transient Earth Engine 503 errors were retried.

## Sources and citations
- REDIAM, burnt areas of Andalusia (WFS, layer `Area_afectada_historico`):
  https://www.juntadeandalucia.es/medioambiente/mapwms/REDIAM_WFS_area_recorrida_fuego
- Martínez-Murillo et al. (2016), Pirineos 171, doi:10.3989/pirineos.2016.171008; Martínez-Murillo et al. (2015),
  EGU2015-1442: https://meetingorganizer.copernicus.org/EGU2015/EGU2015-1442.pdf; Catalina Mimendi (2019):
  https://dialnet.unirioja.es/descarga/articulo/7235486.pdf
- EFDA v2.1.1: Viana-Soto & Senf (2025), doi:10.5194/essd-17-2373-2025; data doi:10.5281/zenodo.13333034.
- Method: Marcos et al. (2023), doi:10.1016/j.rse.2022.113441; Miller & Thode (2007), doi:10.1016/j.rse.2006.12.006;
  Martín-Ortiz et al. (2026), doi:10.3390/rs18091352; Fernández-García et al. (2018), doi:10.1016/j.rse.2017.12.029;
  Cansler & McKenzie (2012), doi:10.3390/rs4020456; Díaz-Delgado et al. (2002),
  doi:10.1890/0012-9658(2002)083[2293:SEODRI]2.0.CO;2; Fernández-Manso et al. (2016), doi:10.1016/j.rse.2016.06.015;
  Yang et al. (2017), doi:10.1016/j.rse.2017.07.022; Yi et al. (2013), doi:10.3390/rs5126938.
- Recovery: Abdul Malak & Pausas (2006), doi:10.1071/wf05052; Viana-Soto et al. (2020), doi:10.3390/rs12091499;
  Viana-Soto et al. (2017), doi:10.3390/environments4040090; Vlassova et al. (2014), doi:10.3390/rs6076136;
  Veraverbeke et al. (2012), doi:10.1071/wf10075; Gómez Zotano et al. (2024), doi:10.1186/s42408-024-00280-0.
- Cite MonitorEO (doi:10.5281/zenodo.23814894), Google Earth Engine (Gorelick et al. 2017,
  doi:10.1016/j.rse.2017.06.031) and the references and credits that each result returns (in `llamadas/<id>.json`).

## Files
Under <everest>/resultados/sierra_de_las_nieves/: `llamadas.json` (41 calls),
`llamadas/<id>.json`, `monitoreo/`, `zonas.gpkg`, `perimetros/` (REDIAM, satellite perimeters, exclusions,
`afectada_limpia.gpkg`), `series_<VAR>_Landsat_filtrada[_sin2023].csv`, `metricas_<VAR>_Landsat[_sin2023].json`
and `.png`, `mapa_severidad_dnbr_1991.png`, `filtrar_serie.py`, `fuentes/` (REDIAM, EFFIS, EFDA, Hansen). Viewer
report draft: <everest>/visor/sierra_de_las_nieves.yaml (id
`2026-11-everest-sierra-de-las-nieves-incendio-1991`); publication to the site is not recorded in the park's json.
