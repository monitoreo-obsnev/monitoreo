---
name: everest-sierra-nevada-fire-2005
description: Lanjaron wildfire of 22-24 September 2005 in Sierra Nevada (Granada, Spain), a crown fire in pine plantations, shrubland and pasture, 3,381 ha official perimeter (1,090 ha in the National Park). Burn severity with Landsat 5 TM (dNBR, one-year RdNBR) without the Landsat water mask, contrast with the official area, MCD64A1 and FireCCI51, and 21 years of recovery of NDVI, LSWI, LST and albedo of Landsat and EVI, LAI, ET, LST, SCD and SMOD of MODIS in the burned area against an elevation-matched control ring, with the metrics of Marcos et al. (2023) and a 10-year reference. Use it to repeat this case (it is the worked example of MonitorEO's manual) or to adapt it to a fire with an official perimeter in a mountain pine plantation, including the snow dimension.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  park: Sierra Nevada National Park
  wdpa_id: "389011"
  event: "sierra_nevada_incendio_2005"
  event_date: "2005-09-22"
  disturbance: fire
  status: validated
  monitoreo_version: "0.3.86"
---

# Lanjaron fire, Sierra Nevada, September 2005

> **Files of this recipe.** `<everest>` is the folder of the EVEREST project where this case was computed: its
> zones (`resultados/<park>/*.gpkg`), its local scripts (`herramientas/`, `scripts/`) and its state files are not part of
> MonitorEO. To repeat the case, rebuild them with MonitorEO: the affected area from the official perimeter
> (`{"ems": ...}`, `{"effis_id": ...}`, `{"wfs": ...}`) or from `burn_severity` with `perimeter: true`, the control
> with `control_ring` (or `ring: true`), and the series and metrics with the calls marked «now». See
> `monitoreo-disturbance-case-study` for the method.

## Question
How severe was the 2005 Lanjaron fire inside and outside the National Park, and, 21 years later, have carbon, water,
energy and snow returned to their pre-fire state relative to unburned land nearby, or has the pine plantation shifted
to another state? It informs post-fire management (salvage logging vs non-intervention, restoration of the
plantations) and which dimensions to monitor.

## Region and periods
- Affected area: the official perimeter provided by the project,
  `<everest>/resultados/lanjaron_fire_perimeter/lanjaron_fire_perimeter.shp` (EPSG:3042,
  one polygon of 3,381.3 ha, FECHA_INIC 20050922, FECHA_FIN 24/09/2005, SUPERFICIE 2,394 ha; read only, never modify).
  1,089.6 ha (32.2 %) inside the National Park (`perimetro_oficial_en_PN.gpkg`).
- Control: ring of 2,000 m at 200 m from the perimeter (`herramientas/zonas.py --perimetro ... --separacion 200
  --ancho 2000`), 7,077.4 ha (2,583.1 ha in the National Park). Both in `zonas.gpkg` (regions `afectada`, `control`).
  `where` in every series: `[{"variable": "ELEVATION", "sensor": "Copernicus", "min": 1300, "max": 2292},
  {"landcover": "CORINE", "year": 2000, "exclude": ["water", "built", "cropland", "bare"]}]` (p5-p95 of the affected
  elevation; pre-fire land cover, because 20 % of the ring was cropland and 15 % bare in 2000). Snow: band 2,000-2,470 m.
- Periods: severity before 2005-06-15/09-20, after 2005-09-25/11-30 (dNBR) and 2006-06-15/09-20 (RdNBR); Landsat
  series 1984-03-16 to 2026-10-31; MODIS from 2000 (LAI from 2002-07-04). Reference of the metrics: 10 years for
  Landsat (1995-10 to 2005-09), 5 for MODIS EVI, ET, LST and snow, 3 for LAI.
- Sensors and why: Landsat 5 TM for the event (20 years before, ~37,800 pixels); Landsat 8/9 after the gap
  2012-05-05/2013-03-18; MODIS as a single-sensor check of the long trends. `"quality": {"water": false}` in every
  Landsat call (see Pitfalls).

## Steps
1. (now) `image_count` of Landsat NDVI 1995-2006 over the perimeter, `"step": "monthly"`. Not run in this case.
2. Burn severity (ids `sev_dnbr_{bbox,pn,zonas,zonas_pn}_nw`, the `_nw` ones are the valid ones):
   ```json
   {"tool": "burn_severity", "args": {"region": {"bbox": [-3.58, 36.9, -3.38, 37.06]}, "sensor": "Landsat",
    "start": "2005-06-15", "end": "2005-09-20", "other_start": "2005-09-25", "other_end": "2005-11-30",
    "perimeter": true, "quality": {"water": false}}}
   ```
   Then `"region": {"wdpa_id": 389011}` with `"perimeter": true`; `"region": {"file": "<everest>/resultados/sierra_nevada/zonas.gpkg", "name_field": "region"}`
   with and without `"within": {"wdpa_id": 389011}`. RdNBR: same zones with `"index": "RdNBR", "other_start":
   "2006-06-15", "other_end": "2006-09-20"` (ids `sev_rdnbr_zonas[_pn]_nw`). **Now**: give the official perimeter
   directly as region (`{"file": ".../lanjaron_fire_perimeter.shp"}`), `"largest": true` in the bbox call, and
   `"offset_region": <the control ring>` for the RdNBR (the manual gives an offset of 0.027 for this fire).
3. Independent burned-area products (Earth Engine data by ID):
   ```json
   {"tool": "area_by_class", "args": {"region": {"file": "<everest>/resultados/sierra_nevada/zonas.gpkg", "name_field": "region"},
    "collection": "MODIS/061/MCD64A1", "band": "BurnDate", "start": "2005-09-01", "end": "2005-10-31",
    "metric": "max", "breaks": [1, 258, 264, 268, 274, 305]}}
   ```
   Same with the bbox, with `"collection": "ESA/CCI/FireCCI/5_1"`, and with `"breaks": [1]` for 2000-11-01/2005-08-31
   and 2005-11-01/2026-09-01 (reburns). Also `region_stats` of ELEVATION (p5, p95) and `area_by_class` with
   `"landcover": "CORINE", "year": 2000, "other_year": 2006` over the zones.
4. Control: built with `herramientas/zonas.py`. **Now**:
   ```json
   {"tool": "control_ring", "args": {"region": {"file": "<everest>/resultados/lanjaron_fire_perimeter/lanjaron_fire_perimeter.shp"},
    "gap": 200, "width": 2000}}
   ```
   (the defaults 150/1,500 give a ring of 5,142 ha and the same match, 1,300-2,292 m, per the manual). Add the CORINE
   2000 condition to the returned `where`.
5. Monthly series (ids `ts_<var>_landsat`, `ts_<var>_modis`): NDVI, LSWI, LST, ALBEDO (and NBR, stopped) of Landsat:
   ```json
   {"tool": "time_series", "args": {"region": {"file": "<everest>/resultados/sierra_nevada/zonas.gpkg", "name_field": "region"},
    "variable": "NDVI", "sensor": "Landsat", "start": "1984-03-16", "end": "2026-10-31", "step": "monthly",
    "scale": 60, "where": <the where above>, "quality": {"water": false}}}
   ```
   MODIS (no `scale`, no `quality`): EVI from 2000-02-18, LAI from 2002-07-04, ET from 2000-01-01, LST from 2000-02-24.
   Snow: `"variable": "SCD", "step": "annual", "metric": "days"` and `"variable": "SMOD", "metric": "melt"`, with the
   elevation condition `"min": 2000, "max": 2470`.
6. Seasonal curves: `compare_series` of Landsat NDVI 1995-01-01/2004-12-31 vs 2006-01-01/2011-12-31 and vs
   2016-01-01/2025-12-31; MODIS EVI 2000-02-18/2004-12-31 vs 2016-2025 (`"step": "monthly"`).
7. Trends: `trend_table` annual of NDVI 1985-2004 and 2006-2025, LSWI and MODIS EVI 2006-2025; per pixel
   `area_by_class` with `"trend": true, "step": "annual"` for NDVI 2006-2025 and EVI 2006-2025, and for NDVI
   2013-03-18/2025-12-31 over `zona_afectada.gpkg` (Landsat 8/9 only, no sensor jump).
8. Recovery metrics: `herramientas/metricas_recuperacion.py --evento 2005-09-22 --afectada afectada --control control
   --anios-ref 10` (5 or 3 for MODIS) on each CSV. **Now**, one call per variable:
   ```json
   {"tool": "recovery_metrics", "args": {"region": {"file": "<everest>/resultados/lanjaron_fire_perimeter/lanjaron_fire_perimeter.shp"},
    "ring": {"gap": 200, "width": 2000}, "variable": "NDVI", "sensor": "Landsat", "start": "1984-03-16",
    "end": "2026-10-31", "event": "2005-09-22", "step": "monthly", "scale": 60, "reference_years": 10,
    "quality": {"water": false, "harmonize": true},
    "where": [{"landcover": "CORINE", "year": 2000, "exclude": ["water", "built", "cropland", "bare"]}]}}
   ```
   (`ring` builds the ring and adds the elevation match; it takes `true` (150/1,500 m) or the options of
   `control_ring` (`gap`, `width`, `exclude`, `within`, `match`); the manual reports S95 0.15, a 61 % drop and RRT 6.6 years
   for this call with the default ring, as in this case). `harmonize` was not used in the case (the sensor jump was
   handled with the difference): with it, expect different absolute numbers.
9. (now) `recovery_map` of Landsat NDVI over the perimeter, a summer `season` (e.g. `["07-01", "09-30"]`; the
   manual does not say which months it used), `"resolution": 60`, `"start": "1999-01-01"`, `"end": "2025-12-31"`,
   `"event": "2005-09-22"`: the manual reports, for the summers of 1999-2025 at 60 m, 62 % of the pixels back in their
   reference, in a median of 4.8 years. Not run in the case.

## Results to expect
From `estado/parques/sierra_nevada.json` (`analisis`) and the files named:
- dNBR (water mask off) in the perimeter: low 602.4, moderate-low 1,041.8, moderate-high 947.3, high 587.6 ha; burned
  3,179.1 ha (94 %), median 0.41; in the National Park 1,045.4 ha burned, median 0.51 vs 0.37 outside.
- RdNBR in the perimeter: unchanged 360.7, low 1,063.7, moderate 1,263.4, high 696.0 ha (median 0.38).
- Area: dNBR ≥ 0.1 +32.8 % vs 2,394 ha official, −6.0 % vs the 3,381.3 ha polygon; burn_severity perimeter touching
  the official one 3,682.2 ha (+8.9 %, IoU 0.84); MCD64A1 3,587.5 ha, 89.8 % dated 2005-09-21 to 09-24; FireCCI51
  3,162.9 ha.
- NDVI Landsat (`metricas_NDVI_Landsat.json`): S95 0.1524, −61.3 %, −9.28 MAD, DIT 0.52, RRT 6.61 years (in the
  Landsat gap); difference −27.24 MAD, no RRT, RET 15.52 years, 50.5 % recovered.
- Difference affected − control, impact in MAD and % recovered: EVI −18.0 / 58.6; LAI −18.6 / 53.9; ET −19.0 / 65.2;
  LSWI −25.5 / 65.3; LST Landsat +16.9 / 68.7; LST MODIS +12.7 / 92.0 (RRT 20.69 years, at the series edge);
  ALBEDO −6.5 (then above its pre-fire relation); SCD +1.4 and SMOD −1.4 (`metricas_*.json`).
- Trends: NDVI 1985-2004 +0.0062/yr (affected) and +0.0030 (control); 2013-2025 per pixel: 26 % up, 11 % down.
- Extension (HFT of eHabitat+, `analisis_hft`, `resultados/sierra_nevada/hft/`): NDVI resilience Q at 19-21 years 93 %
  (low), 87 % (moderate-low), 82 % (moderate-high), 64 % (high severity).

## Pitfalls
- Landsat's QA water bit flagged 433 ha (12.8 %) of the dark charred perimeter as water after the fire; high severity
  fell from 588 to 454 ha. Use `"quality": {"water": false}` and mask real water with CORINE.
- Summer-to-autumn change makes 13 % of the control (930 ha) pass dNBR 0.1, and the drought of 2005 vs 2006 puts
  1,749 ha of the control in the low RdNBR class: use thresholds ≥ 0.27, the perimeter, or now `offset_region`.
- The official area (2,394 ha, burned vegetation) and the polygon (3,381.3 ha) do not measure the same; sources give
  2,600-3,500 ha.
- The Landsat 5/7 → 8/9 jump (+0.05 NDVI affected, +0.075 control) and the 2012-2013 gap: absolute RRTs of NDVI and
  LSWI fall in the gap and are not reliable; use the difference (or now `harmonize`).
- The reference includes the extreme drought of 2005; the local script could not exclude years.
- Albedo has two phases (charcoal darkening, then brighter than the pine canopy): one-direction metrics miss it.
- Where cannot use aspect; snow has only ~35 MODIS pixels; salvage logging (~7 months after) is mixed with recovery.
- The series by severity class (`ts_ndvi_landsat_severidad`, monthly and annual) did not finish (Earth Engine 503):
  pending. The NBR series was stopped.

## Sources and citations
- Official perimeter (provided by the project, `resultados/lanjaron_fire_perimeter/`); REDIAM CIR orthophoto of the fire
  (2005-10-06): https://portalrediam.cica.es/geonetwork/static/api/records/865a890f538ccb8cd7ce0a9d63ffaa3baaaa4977 ;
  EFFIS, Forest Fires in Europe 2005:
  https://data.effis.emergency.copernicus.eu/effis/reports-and-publications/annual-fire-reports/03-forest-fires-in-europe-2005.pdf ;
  Zamora et al. (eds., 2015), OBSNEV: https://ecologia.ugr.es/sites/dpto/ecologia/public/inline-images/Huella-Cambio-Global.pdf
- Event: Mesa Garrido (2019), doi:10.14198/INGEO2019.71.10; Molinas-González et al. (2017), doi:10.3390/f8050158;
  Molinas-González et al. (2019), doi:10.3390/f10111046; Castro & Leverkus (2019), doi:10.3390/f10010074.
- Recovery: Fernández-Manso et al. (2016), doi:10.1016/j.rse.2016.06.015; Viana-Soto et al. (2020),
  doi:10.3390/rs12091499; Vilà-Cabrera et al. (2011), doi:10.1111/j.1365-2699.2011.02615.x; Pausas et al. (2008),
  doi:10.1071/wf07151; Karavani et al. (2018), doi:10.1002/ecm.1285; Castro et al. (2010),
  doi:10.1111/j.1523-1739.2009.01382.x; Castro et al. (2011), doi:10.1111/j.1526-100x.2009.00619.x; Castro et al.
  (2012), doi:10.1890/es12-00089.1; Leverkus & Castro (2017), doi:10.1002/eap.1539; Leverkus et al. (2016),
  doi:10.1002/ecy.1527; Marañón-Jiménez et al. (2013), doi:10.1071/wf12030; Serrano-Ortiz et al. (2011),
  doi:10.1016/j.foreco.2011.08.023; Micheletty et al. (2014), doi:10.5194/hessd-11-7513-2014.
- Method: Marcos et al. (2023), doi:10.1016/j.rse.2022.113441; Fernández-García et al. (2018),
  doi:10.1016/j.rse.2017.12.029; Peña-Molina et al. (2024), doi:10.3390/rs16101718; Díaz-Delgado et al. (2002),
  doi:10.1890/0012-9658(2002)083[2293:SEODRI]2.0.CO;2; Lhermitte et al. (2011), doi:10.1016/j.isprsjprs.2010.08.004;
  Morresi et al. (2019), doi:10.3390/rs11030308; Vlassova et al. (2014), doi:10.3390/rs6076136.
- Cite MonitorEO (doi:10.5281/zenodo.23814894), Google Earth Engine (Gorelick et al. 2017,
  doi:10.1016/j.rse.2017.06.031) and the references and credits that each result returns (in `llamadas/<id>.json`).

## Files
Under <everest>/resultados/sierra_nevada/: `llamadas.json` (43 calls),
`llamadas/<id>.json`, `monitoreo/`, `zonas.gpkg`, `zona_afectada.gpkg`, `zonas_severidad.gpkg`,
`perimetro_oficial_en_PN.gpkg`, `perimetro_satelite_dnbr027*.gpkg`, `severidad_contraste_perimetro*.json`,
`metricas_<VAR>_<sensor>.{json,png}`, `mapa_severidad_dNBR_Landsat.png`, `lote*.log`, `hft/`. Viewer reports:
<everest>/visor/sierra_nevada.yaml (id `2026-11-everest-sierra-nevada-incendio-2005`;
publication not recorded) and visor/sierra_nevada_hft.yaml (published 2026-11-28, monitoreo-obsnev/resultados commit
8107dc9, report `2026-11-everest-sierra-nevada-incendio-2005-hft`, with MonitorEO 0.3.92).
