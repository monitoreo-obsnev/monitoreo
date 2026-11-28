---
name: everest-picos-de-europa-late-frost-2017
description: Late spring frost of late April 2017 in the beech and oak forests of Picos de Europa National Park (Spain), followed by a hot dry summer. Delimits the defoliated forest without an official perimeter by the standardized anomaly (z) of MODIS NDVI of May-June, builds an elevation- and aspect-matched control, and measures sensitivity and recovery (S95, DIT, RRT, RET of Marcos et al. 2023) of NDVI, EVI, LAI, ET, NDWI, LST and albedo of MODIS at 16 days, with Sentinel-2 as an independent check and SMOD as a covariate. Use it to repeat this case or to adapt it to a short, non-lethal canopy disturbance (late frost, defoliation, hail, drought browning) in a deciduous forest where there is no perimeter and the signal lasts only weeks.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  park: Picos de Europa National Park
  wdpa_id: "71213"
  event: "picos_de_europa_helada_2017"
  event_date: "2017-04-25 (assumed; the sources only say «late April»; event window 2017-04-20 to 2017-09-30)"
  disturbance: frost
  status: validated
  monitoreo_version: "0.3.86"
---

# Late spring frost in the beech forests of Picos de Europa, 2017

> **Files of this recipe.** `<everest>` is the folder of the EVEREST project where this case was computed: its
> zones (`resultados/<park>/*.gpkg`), its local scripts (`herramientas/`, `scripts/`) and its state files are not part of
> MonitorEO. To repeat the case, rebuild them with MonitorEO: the affected area from the official perimeter
> (`{"ems": ...}`, `{"effis_id": ...}`, `{"wfs": ...}`) or from `burn_severity` with `perimeter: true`, the control
> with `control_ring` (or `ring: true`), and the series and metrics with the calls marked «now». See
> `monitoreo-disturbance-case-study` for the method.

## Question
Where and how strongly did the late-April 2017 frost defoliate the beech (Fagus sylvatica) and oak (Quercus petraea,
Q. pyrenaica) forests of the park, can it be told apart from the summer drought of 2017, and how fast did each
ecosystem function (carbon, water, energy) recover? It informs whether the frost-prone upper beech belt (1,200-1,600 m)
needs specific monitoring, and whether the satellite sees what the OAPN phytosanitary network recorded in the field
(mean defoliation of the park 26.4 % in 2017, 21.6 % in 2018, ~21 % in 2019).

## Region and periods
- Affected area: `{"file": "<everest>/resultados/picos_de_europa/zonas.gpkg",
  "name_field": "region", "within": {"wdpa_id": 71213}}`, region `afectada` (2,362.9 ha). Made locally, no official
  perimeter: forest pixels of the park (CORINE 2018, trees only) with z ≤ −2 of MODIS NDVI (median 9 May-25 June 2017
  vs 2003-2016), clusters of ≥ 2 pixels of 250 m, minus EFFIS perimeters 2000-2026 with a 100 m margin
  (`scripts/anomalia_primavera_2017.py`, `scripts/zonas_y_parcelas.py`; detail in `zonas_delimitacion.json`).
- Control: region `control` (758.7 ha), drawn by hand (`herramientas/zonas.py --control-fichero`): forest of the park
  with z > −0.5 in 2017, in the elevation band of the affected area (p5-p95 = 1,214-1,574 m), > 250 m from it, with
  the same share of aspects (stratified sample, seed 1). The automatic ring was rejected: the forest around the affected
  area is lower or also affected. `where` in every series: `[{"variable": "ELEVATION", "sensor": "Copernicus",
  "min": 1214, "max": 1574}]`.
- Periods: reference 2003-2016 (z maps and seasonal curve); metrics with a 3-year reference before 2017-04-25;
  series to 2026-10-31. Windows: spring 9 May-25 June (frost) and summer 12 July-29 September (drought).
- Sensors and why: MODIS (250 m NDVI/EVI, 16 days) is the reference sensor for frost defoliation (daily revisit; the
  signal lasts 10-12 weeks; Olano et al. 2021). Landsat had few clear dates in the cloudy Atlantic spring of 2017;
  Sentinel-2 (from 2017-03-28) has no pre-event reference of its own and is used only as a check (2017 vs 2018).

## Steps
1. (now) Check the data first: `image_count`, e.g.
   `{"tool": "image_count", "args": {"region": {"wdpa_id": 71213}, "variable": "NDVI", "sensor": "MODIS",
   "start": "2003-01-01", "end": "2019-12-31", "step": "16-day"}}`. Not run in this case (the tool did not exist).
2. Yearly z maps of spring NDVI (one call per year 2003-2019, ids `di_ndvi_modis_primavera_<year>`; the same for summer
   2003-2017 with `"start": "<year>-07-12", "end": "<year>-09-29"`, ids `di_ndvi_modis_verano_<year>`):
   ```json
   {"tool": "download_image", "args": {"region": {"wdpa_id": 71213}, "variable": "NDVI", "sensor": "MODIS",
    "start": "2017-05-09", "end": "2017-06-25", "metric": "median", "resolution": 250, "crs": "EPSG:25830",
    "where": [{"landcover": "CORINE", "year": 2018, "exclude": ["water", "grassland", "wetland", "cropland",
    "shrubland", "built", "bare", "snow"]}]}}
   ```
   plus the DEM: `{"tool": "download_image", "args": {"region": {"wdpa_id": 71213}, "variable": "ELEVATION",
   "sensor": "Copernicus", "resolution": 250, "crs": "EPSG:25830"}}`. The z per pixel (2017 vs 2003-2016) was computed
   locally (`scripts/anomalia_primavera_2017.py`, `anomalia_verano_2017.py`).
   **Now**: one call, `download_comparison` (or `compare_map`) with `"z": true`, reference 2003-2016 and other period
   2017, `season: ["05-09", "06-25"]`, same `where` (documented in the manual, section «Comparison of two periods»;
   check your server has `z`). Then threshold z ≤ −2 and vectorize.
3. Zones: `herramientas/zonas.py --control-fichero` (hand-drawn control, see above). **Now**: `control_ring` /
   `ring: true` would give a ring matched by elevation, but here it is not the same ecosystem: keep a hand-drawn
   control and pass `"affected": "afectada", "control": "control"` to `recovery_metrics`.
4. Series of 16 days, 2003-01-01 to 2026-10-31, for NDVI, EVI, LAI, ET, LST, ALBEDO (ids `ts_<var>_modis_16d`):
   ```json
   {"tool": "time_series", "args": {"region": {"file": "<everest>/resultados/picos_de_europa/zonas.gpkg",
    "name_field": "region", "within": {"wdpa_id": 71213}}, "variable": "NDVI", "sensor": "MODIS",
    "start": "2003-01-01", "end": "2026-10-31", "step": "16-day",
    "where": [{"variable": "ELEVATION", "sensor": "Copernicus", "min": 1214, "max": 1574}]}}
   ```
   NDWI (MODIS daily NDWI ends 2023-02): same with `"start": "2010-01-01", "end": "2023-02-15", "season": ["04-01",
   "10-31"]`. Snow melt-out day: `"variable": "SMOD", "step": "annual", "metric": "melt"`. Sentinel-2 check:
   `"variable": "NDVI", "sensor": "Sentinel-2", "start": "2017-03-28", "step": "monthly"` (and `"16-day"`), `"scale": 20`.
5. Seasonal curve and anomaly of 2017: `compare_series` with `"start": "2003-01-01", "end": "2016-12-31",
   "other_start": "2017-01-01", "other_end": "2017-12-31", "step": "16-day"` (NDVI and EVI), and 2018-2025 vs
   2003-2016 with `"step": "monthly"` (ids `cs_*`).
6. Trends by window: `trend_table` with `"step": "annual"` and `"season": ["05-09", "06-25"]` or `["07-12", "09-29"]`,
   for 2003-01-01/2016-12-31 and 2018-01-01/2026-10-31 (ids `tt_ndvi_modis_{primavera,verano}_{pre,post}`).
7. Independent sensor check (bbox of the south-west sector):
   ```json
   {"tool": "download_comparison", "args": {"region": {"bbox": [-5.06, 43.08, -4.84, 43.2]}, "variable": "NDVI",
    "sensor": "Sentinel-2", "start": "2018-05-09", "end": "2018-06-25", "other_start": "2017-05-09",
    "other_end": "2017-06-25", "resolution": 20}}
   ```
   and the same with `compare_map` (`"vmin": -0.3, "vmax": 0.3`) for the figure; summarized with `scripts/s2_contraste.py`.
8. Recovery metrics: run locally with `herramientas/metricas_recuperacion.py` on each 16-day CSV
   (`--evento 2017-04-25 --afectada afectada --control control`, 3 reference years); seasonal windows with
   `scripts/ventanas_estacionales.py`. **Now**:
   ```json
   {"tool": "recovery_metrics", "args": {"region": {"file": "<everest>/resultados/picos_de_europa/zonas.gpkg",
    "name_field": "region", "within": {"wdpa_id": 71213}}, "affected": "afectada", "control": "control",
    "variable": "NDVI", "sensor": "MODIS", "start": "2003-01-01", "end": "2026-10-31", "event": "2017-04-25",
    "step": "16-day", "reference_years": 3,
    "where": [{"variable": "ELEVATION", "sensor": "Copernicus", "min": 1214, "max": 1574}]}}
   ```
   Repeat for EVI, LAI, ET, NDWI (to 2023-02-15), LST, ALBEDO. z per step: (now) `anomalies`, if your server has it.
9. (optional, now) Where it recovered: `recovery_map` is annual per pixel; with a signal of weeks use the spring
   season only (`"season": ["05-09", "06-25"]`), and expect little, since the canopy refoliated within the year.

## Results to expect
From `estado/parques/picos_de_europa.json` (`analisis`) and the files named:
- Affected area 2,362.9 ha (2,487 ha before removing EFFIS perimeters; 1,263-5,106 ha for z thresholds −3 to −1),
  1,214-1,574 m, median 1,401 m, 56 % north-facing (`zonas_delimitacion.json`, `anomalia_primavera_2017.json`).
- z of 2017 spring NDVI by elevation band: median −1.09 (29.7 % of pixels ≤ −2) at 1,200-1,500 m and −1.49 (37.7 %)
  at 1,500-1,800 m; positive below 1,200 m.
- NDVI MODIS (`metricas_NDVI_MODIS.json`): affected S95 −0.13, −11.2 %, −3.24 MAD, RRT 0.43 years; difference
  affected − control −3.83 MAD, tINF 2017-05-09, RRT 0.43, RET 1.04 years. z of the difference −7.05 in the composite
  of 25 May 2017; back to |z| < 1 on 28 July 2017.
- Impact of the difference in MAD: LAI −7.39, NDWI −5.23, EVI −4.44, ET −4.33, LST +4.21, ALBEDO −3.87, NDVI −3.83.
  RRT of the difference (years): LST 0.08, ET 0.26, EVI 0.30, NDVI 0.43, ALBEDO 0.52, LAI 0.61, NDWI 1.95
  (`metricas_<VAR>_MODIS.json`).
- Frost vs drought (`ventanas_<VAR>_MODIS.json`): spring z of the difference NDVI −5.24; summer NDWI z −3.30
  (affected) and −2.84 (control), i.e. the drought hit both zones. Spring 2018 difference still z −2.09 (NDVI),
  2019 normal (−0.35).
- Sentinel-2 (`contraste_sentinel2.json`): median ΔNDVI (2017 − 2018) −0.060 in the affected area (633 ha below −0.1)
  vs +0.024 in the control.
- SMOD 2017: day 52 in the affected area vs 88 ± 20 in 2003-2016 (z −1.85).

## Pitfalls
- No perimeter: the affected area is chosen with the 2017 NDVI itself, so the spring anomaly is partly circular.
  Independent evidence used: timing at 16 days, Sentinel-2, elevation band and sector matching the sources, and no
  pre-event trend of the difference (τ 0.30, p 0.15).
- The frost date is not in the sources («late April»); 2017-04-25 was assumed. Pending: fix it with ERA5-Land or AEMET
  minimum temperatures.
- The control ring was not the same ecosystem; a hand-drawn control matched by elevation and aspect was needed.
  `download_image` of the aspect failed (call `di_aspect_250`: unit `m` given for an aspect in degrees), so aspect was
  computed locally.
- STL with a one-year window smooths a signal of weeks: RRT 0.43 years vs a direct return of z to |z| < 1 after ~0.25
  years. Read both.
- 500 m and 1 km variables (LAI, ET, NDWI, ALBEDO, LST) mix the affected area with its surroundings: conservative
  impacts. MODIS NDWI (MOD09GA_006_NDWI) stops in 2023-02.
- Spring 2018 was also anomalous (possible new frost) and overlaps the recovery. EFDA v2.1.1 does not see the frost
  (2.4 ha disturbed in 2017): frost does not kill the trees.
- No MonitorEO warnings in any result.

## Sources and citations
- OAPN-MITECO, phytosanitary monitoring 1986/2017:
  https://www.miteco.gob.es/content/dam/miteco/es/parques-nacionales-oapn/red-parques-nacionales/seguimiento/informe-fitosanitario-2017_tcm30-484093.pdf
- OAPN-MITECO, phenology 2008/2017 («a finales de abril una extensa helada tardía»):
  https://www.miteco.gob.es/content/dam/miteco/es/parques-nacionales-oapn/red-parques-nacionales/seguimiento/fenologia-2017_tcm30-502374.pdf
- OAPN-MITECO, phytosanitary 1986/2018 and 2019 results:
  https://www.miteco.gob.es/content/dam/miteco/es/parques-nacionales-oapn/red-parques-nacionales/seguimiento/informe-fitosanitario-2018_tcm30-509180.pdf ;
  https://www.miteco.gob.es/content/dam/miteco/es/parques-nacionales-oapn/red-parques-nacionales/seguimiento/0221_08informe_resultados_2019_fitosanitario_difusion-srdrjs442022_tcm30-539095.pdf
- Olano et al. (2021), Ecological Applications, doi:10.1002/eap.2288; Sangüesa-Barreda et al. (2021), Foresta 81 (no
  DOI): https://www.forestales.net/revistas/articulos/550/completo/los_danos_por_heladas_tardias_en_los_hayedos_iberi.pdf
- Method: Marcos et al. (2023), doi:10.1016/j.rse.2022.113441; Nolè et al. (2018), doi:10.1007/s13595-018-0763-1;
  Allevato et al. (2019), doi:10.1016/j.rse.2019.03.023; Buras et al. (2021), doi:10.3389/fpls.2021.689220;
  Hufkens et al. (2012), doi:10.1111/j.1365-2486.2012.02712.x; Wright et al. (2024), doi:10.3390/rs16183477.
  Recovery: Menzel et al. (2015), doi:10.3389/fpls.2015.00110; Zohner et al. (2018), doi:10.1111/nph.15445;
  Baumgarten et al. (2023), doi:10.1111/1365-2435.14243; Greco et al. (2018), doi:10.3390/f9070388.
- Cite MonitorEO (doi:10.5281/zenodo.23814894), Google Earth Engine (Gorelick et al. 2017,
  doi:10.1016/j.rse.2017.06.031) and the references and credits that each result returns (in `llamadas/<id>.json`).

## Files
Under <everest>/resultados/picos_de_europa/: `llamadas.json` (52 calls) and
`llamadas/<id>.json` (responses), `monitoreo/` (CSV, PNG, GeoTIFF, README), `zonas.gpkg`, `zonas.geojson`,
`zonas_delimitacion.json`, `anomalia_primavera_2017.json`, `anomalia_verano_2017.json`, `contraste_sentinel2.json`,
`metricas_<VAR>_MODIS.{json,png}`, `ventanas_<VAR>_MODIS.json`, `mapa_z_ndvi_primavera_2017.png`, `scripts/`,
`fuentes/` (OAPN PDFs, EFDA). Viewer report draft: <everest>/visor/picos_de_europa.yaml
(id `2026-11-everest-picos-de-europa-helada-2017`); whether it was published to the site is not recorded in the
park's json. Summary in <everest>/informe_perturbaciones.html.
