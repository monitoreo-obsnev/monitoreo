---
name: everest-ordesa-avalanche-1996
description: Destructive snow avalanche of La Canal (winter 1995-96) in the Ordesa valley, Ordesa y Monte Perdido National Park, which destroyed a strip of Scots pine forest. Dating of the event with Landsat 5 summer composites and daily images, delineation of a 6.6 ha affected zone by anomaly (no published perimeter), a control on the same slope matched by elevation and aspect, Landsat summer series of NBR, NDVI, EVI, LSWI, LST and albedo (1984–2025), Sentinel-2 for the current state, and Marcos et al. (2023) recovery metrics with a BACI difference over three decades. Use it to repeat this case or to adapt it to a small, old disturbance (avalanche, windthrow, landslide) with an uncertain date.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  park: Parque Nacional de Ordesa y Monte Perdido
  wdpa_id: "893"
  event: "ordesa_alud_1996"
  event_date: "1995-11-23/1996-02-27 (satellite window); nominal 1996-02-09 for the metrics"
  disturbance: other  # snow avalanche
  status: validated
  monitoreo_version: "0.3.86"
---

# Avalanche of La Canal, Ordesa valley, winter 1995-96

> **Files of this recipe.** `<everest>` is the folder of the EVEREST project where this case was computed: its
> zones (`resultados/<park>/*.gpkg`), its local scripts (`herramientas/`, `scripts/`) and its state files are not part of
> MonitorEO. To repeat the case, rebuild them with MonitorEO: the affected area from the official perimeter
> (`{"ems": ...}`, `{"effis_id": ...}`, `{"wfs": ...}`) or from `burn_severity` with `perimeter: true`, the control
> with `control_ring` (or `ring: true`), and the series and metrics with the calls marked «now». See
> `monitoreo-disturbance-case-study` for the method.

## Question
When did the La Canal avalanche destroy the forest (the sources disagree: 1995-96 or 1996-97), how large was the
destroyed strip, and has the canopy come back 30 years later, in which functions first? It informs avalanche-path
management and whether the pine forest is being replaced by another vegetation (estado/parques/ordesa.json).

## Region and periods
- Affected area: no published perimeter (the 1:25,000 map of OAPN project 11/2003 is not online). Delimited **locally**
  by anomaly on a stack of summer composites (`scripts/fechado.py`, `scripts/zonas_mascaras.py`, thresholds in
  `resultados/ordesa/analisis/parametros_zonas.json`): 1996 NDVI drop ≤ −0.10 against the median of the 3 previous
  summers, NDVI z ≤ −2.5 against 1985–1995, NBR drop ≤ −0.15, NBR still 0.10 below its 1985–1995 mean in 1997,
  connected to the La Canal gully. Region `afectada` of
  `<everest>/resultados/ordesa/zonas.gpkg` (6.6 ha, 1407–1602 m, aspect 197°); plus 0.9 ha
  of deposit on the valley floor, not in the series.
- Control: region `control` (83.2 ha, 76.5 in the park): pine on the same sunny slope north of the Arazas river, aspect
  ±45°, elevation p5–p95 of the affected zone, pre-event NDVI ≥ its p10, 150–2000 m away, > 60 m from any pixel with an
  NBR drop ≤ −0.20 in 1987–2025 (other avalanche paths) and > 150 m from the 2017-2018 patches (Carriata avalanche).
- where in all series (**W**): `[{"variable": "ELEVATION", "sensor": "Copernicus", "min": 1419, "max": 1580}]`;
  region (**Z**): `{"file": "<everest>/resultados/ordesa/zonas.gpkg", "name_field": "region", "within": {"wdpa_id": 893}}`.
- Periods: summers (July–September) to date and for the main metrics (winter: snow and shadow); series 1984-03-16 →
  2025-12-31; Sentinel-2 2017-03-28 → 2025-12-31. Reference 1984/85–1995.
- Sensors: Landsat 5 (only sensor before 1999) and 8/9; Sentinel-2 for the current state at 10–20 m; MODIS not usable
  (the event predates it and 6.6 ha is far below its pixel). Valley boxes: `[-0.115, 42.63, -0.045, 42.68]` (dating)
  and `[-0.098, 42.65, -0.062, 42.668]` (maps).

## Steps
Run with `herramientas/mcp_calls.py ordesa resultados/ordesa/llamadas.json` (137 calls). B = `{"bbox": [-0.115, 42.63, -0.045, 42.68]}`.

0. «now», not run: images per summer (2–10 with Landsat 5 according to the json; 2 in 2004):
   `{"tool": "image_count", "args": {"region": B, "variable": "NBR", "sensor": "Landsat", "start": "1985-01-01", "end": "2025-12-31", "step": "annual", "season": ["07-01", "09-30"]}}`
1. Before/after maps of the candidate years (1995→1996, 1996→1997, 1990–95→1996):
   `{"tool": "download_comparison", "args": {"region": B, "variable": "NBR", "sensor": "Landsat", "start": "1995-07-01", "end": "1995-09-30", "other_start": "1996-07-01", "other_end": "1996-09-30", "season": ["07-01", "09-30"], "resolution": 30}}`
   (also NDVI); `compare_map` on the small box with `"vmin": -0.3, "vmax": 0.3`; `download_rgb` / `rgb_map` of the summers 1995, 1996, 1997.
2. Stack of summer medians, one GeoTIFF per year 1985–2025 (40 calls per index, NDVI and NBR):
   `{"tool": "download_image", "args": {"region": B, "variable": "NBR", "sensor": "Landsat", "start": "1996-07-01", "end": "1996-09-30", "metric": "median", "resolution": 30}}`;
   DEM `{"tool": "download_image", "args": {"region": B, "variable": "ELEVATION", "sensor": "Copernicus", "resolution": 30}}`.
   Then the **local** first-drop year per pixel and the masks (`fechado.py`, `zonas_mascaras.py`). No MonitorEO tool
   delineates by anomaly; «now» `recovery_map` (step 7) gives a per-pixel impact that can help, and `control_ring`
   (`"gap": 150, "width": 1850`, then ASPECT in where) gives a first control, but the exclusion of other avalanche
   paths and of Carriata is still manual.
3. Zone checks: `region_stats` of ELEVATION (`"stats": ["mean", "min", "p5", "p50", "p95", "max"]`) and SLOPE on Z.
4. Dating image by image (last clear image before, first after):
   `{"tool": "time_series", "args": {"region": Z, "variable": "NBR", "sensor": "Landsat", "start": "1995-01-01", "end": "1997-12-31", "step": "daily", "where": W}}` (and NDVI).
5. Series of the two zones (NDVI, NBR, EVI, LSWI, ALBEDO, LST): monthly and annual summer:
   `{"tool": "time_series", "args": {"region": Z, "variable": "NBR", "sensor": "Landsat", "start": "1984-03-16", "end": "2025-12-31", "step": "annual", "season": ["07-01", "09-30"], "where": W}}`
   and `"step": "monthly"` without season; Sentinel-2 NDVI, NBR, EVI from 2017-03-28; snow:
   `"variable": "SMOD", "step": "annual", "metric": "melt"` and `"variable": "SCD", "metric": "days"`.
6. Reference dynamics: `trend_table` (annual, summer) for 1985–1995, 1997–2011 and 2013-04-01–2025 (NDVI, NBR);
   `compare_series` monthly 1985–1995 vs 1996–2005 and vs 2016–2025; per-pixel recovery:
   `{"tool": "area_by_class", "args": {"region": Z, "variable": "NBR", "sensor": "Landsat", "trend": true, "start": "1997-01-01", "end": "2011-12-31", "step": "annual", "season": ["07-01", "09-30"], "where": W}}`.
7. Recovery metrics: **local** `herramientas/metricas_recuperacion.py` (`scripts/correr_metricas.sh`, event 1996-02-09,
   5 reference summers 1991–1995 for the summer series, 3 years for the monthly ones); BACI z of the summer difference
   against 1984–1995 with `scripts/baci_verano.py`. «now»:
   `{"tool": "recovery_metrics", "args": {"region": {"file": "<everest>/resultados/ordesa/zonas.gpkg", "name_field": "region", "within": {"wdpa_id": 893}}, "affected": "afectada", "control": "control", "variable": "NBR", "sensor": "Landsat", "start": "1984-03-16", "end": "2025-12-31", "event": "1996-02-09", "step": "annual", "season": ["07-01", "09-30"], "reference_years": 5, "where": W}}`
   and, per pixel, `{"tool": "recovery_map", "args": {"region": {"bbox": [-0.098, 42.65, -0.062, 42.668]}, "variable": "NBR", "sensor": "Landsat", "start": "1985-01-01", "end": "2025-12-31", "event": "1996-02-09", "season": ["07-01", "09-30"], "resolution": 30, "reference_years": 5}}`.
8. Figures: `map_layer` with `"figure": true` of NBR Landsat summer 1996 and NDVI Sentinel-2 summer 2025.

## Results to expect
From estado/parques/ordesa.json (`analisis`, `validacion`) and `resultados/ordesa/metricas_*_verano.json`:
- Date: NBR of the affected zone 0.711 on 1995-11-23 (control 0.683) and 0.489 on 1996-02-27 (control 0.690); summer
  NBR 0.370 in 1996 (control 0.684). In a 930 m window, 99 pixels first drop in 1996 and 15 in 1997: winter 1995-96.
- Size: 6.6 ha (73 pixels) plus 0.9 ha on the valley floor; threshold sensitivity 3.5–9.8 ha; width at 1450 m 240 m
  vs 256 m in the OAPN report (−6 %).
- Magnitude, summer 1996: dNBR mean 0.261 (control −0.030); NBR −40.8 % (S95 0.257), LSWI −66.0 %, NDVI −22.9 %,
  EVI −5.3 %, albedo +42.8 %, LST +5.1 %. BACI z 1996: LSWI −30.0, NBR −22.7, NDVI −16.0, albedo +15.2, EVI −5.4, LST +5.0.
- Recovery: NDVI RRT 3.39 years (8.39 against the control; difference back in 2004, 115.5 % in 2021–2025); NBR RRT
  16.39 (20.39 against the control, 101.4 %); LSWI RRT 24.39 but 94 % against the control; albedo not recovered (3 %).
- Per pixel 1997–2011: 98.5 % of the affected zone (5.85 ha) with significant NBR increase vs 36.5 % of the control.
- New state: NDVI seasonal amplitude 0.256 vs 0.071 in the control (Sentinel-2): a deciduous canopy, not pine.

## Pitfalls
- Contradictory dates in the sources; resolved with the daily Landsat 5 series and the summer stack, not with the text.
- Monthly series are 43 % interpolated (snow and shadow January–April): the main metrics use summer series (2.4 % gaps).
- With 5 summers of reference the MAD is tiny and «impact in MAD» explodes (NBR −84 MAD): rank sensitivity with the
  BACI z against 1984–1995 instead.
- Monthly |z| > 2 also appears in the control after 2013 (greening and the TM → OLI change): use the difference.
- RET of the summer series fires on recovery plateaus and is not reliable here; NBR RRT lands on 2012 (gap year,
  interpolated) although 2011 already reached the reference.
- Landsat 5 LST is 120 m: about 5 thermal pixels over 6.6 ha. The delineation depends on the thresholds.
- Four calls failed on arguments (`terrain` does not accept ELEVATION; SCD needs `days`, SMOD `melt`) and were rerun.

## Sources and citations
- OAPN report, Gutiérrez Merino et al. (project 11/2003):
  https://www.miteco.gob.es/content/dam/miteco/images/es/oapn_inv_art_0502_tcm30-65678.pdf ; PNOMP report 2022:
  https://www.aragon.es/documents/d/guest/2022_memoria_pnomp-pdf ; Julián & Chueca 1999, doi:10.26754/ojs_geoph/geoph.1999371401.
- Regional context: Oller et al. 2015, doi:10.1016/j.coldregions.2014.11.012; Furdada et al. 2020, doi:10.3390/geosciences10040126;
  Muntán et al. 2004, doi:10.3189/172756404781815077.
- Method: Marcos et al. 2023, doi:10.1016/j.rse.2022.113441; Hislop et al. 2018, doi:10.3390/rs10030460; Kennedy et al.
  2010, doi:10.1016/j.rse.2010.07.008; White et al. 2017, doi:10.1016/j.rse.2017.03.035; Pickell et al. 2015,
  doi:10.1080/2150704x.2015.1126375; Răchită et al. 2026, doi:10.1016/j.catena.2026.110505; Lai & Oguchi 2022, doi:10.3390/rs14215419.
- Avalanche ecology: Fischer & Lehnert 2011, doi:10.1007/s10531-011-0204-z; Vacchiano et al. 2015,
  doi:10.1016/j.coldregions.2015.03.004; Oven et al. 2020, doi:10.20315/asetl.121.1; Rixen et al. 2007, doi:10.1111/j.1654-1103.2007.tb02588.x.
- Cite MonitorEO (doi:10.5281/zenodo.23814894), Google Earth Engine (doi:10.1016/j.rse.2017.06.031) and the references
  and credits that each result returns (`resultados/ordesa/analisis/referencias_monitoreo.json`).

## Files
- `<everest>/resultados/ordesa/`: `llamadas.json`, `llamadas/`, `monitoreo/`, `zonas.gpkg`,
  `metricas_*_{verano,mensual,anual}.json/png`, `analisis/` (stacks, dating, masks, BACI, seasonality, sensitivity),
  `scripts/`, `fig_dimensiones_baci.png`, `fig_estado_actual.png`.
- State: `estado/parques/ordesa.json`; report `informe_perturbaciones.html`. Not published in the viewer (not recorded).
- Pending: the OAPN 1:25,000 map, Senf & Seidl (2021) map, field check of the current canopy, the Lucas Mallada article
  for the exact date (9 February 1996, unverified).
