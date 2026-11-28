---
name: everest-teide-fire-2023
description: Tenerife wildfire of August 2023 (Arafo-Candelaria, started 2023-08-15) in its part inside Teide National Park (Canary Islands, Spain), summit broom shrubland (Spartocytisus supranubius) and Canary pine at 1,930-2,344 m. Burn severity with Sentinel-2 (dNBR and one-year RdNBR, with the dNBR offset of a control), contrast with Landsat 8/9, MCD64A1 and the Copernicus EMS EMSR685 grading perimeter, and the first 3 years of recovery of NDVI, LSWI and albedo of Sentinel-2, NDVI and LST of Landsat and NDVI, LAI and ET of MODIS against a control ring matched by elevation and pre-fire NDVI, with the metrics of Marcos et al. (2023) (provisional). Use it to repeat this case or to adapt it to a recent fire (Sentinel-2 era, EMS or EFFIS perimeter) in sparse high-mountain shrubland, where the absolute dNBR underestimates severity and a drought year follows the fire.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  park: Teide National Park
  wdpa_id: "389013"
  event: "teide_incendio_2023"
  event_date: "2023-08-15"
  disturbance: fire
  status: validated
  monitoreo_version: "0.3.86"
---

# Tenerife wildfire in Teide National Park, August 2023

> **Files of this recipe.** `<everest>` is the folder of the EVEREST project where this case was computed: its
> zones (`resultados/<park>/*.gpkg`), its local scripts (`herramientas/`, `scripts/`) and its state files are not part of
> MonitorEO. To repeat the case, rebuild them with MonitorEO: the affected area from the official perimeter
> (`{"ems": ...}`, `{"effis_id": ...}`, `{"wfs": ...}`) or from `burn_severity` with `perimeter: true`, the control
> with `control_ring` (or `ring: true`), and the series and metrics with the calls marked «now». See
> `monitoreo-disturbance-case-study` for the method.

## Question
How much of the park burned and how severely (the official figure is 1,235 ha), and how fast are the summit broom
shrubland and the pine stands of El Portillo recovering, once the drought of 2024 is removed with a control? It
informs the restoration works under way (fences against rabbits and mouflon, replanting, removal of damaged pines) and
when to re-assess (the metrics are provisional with 3.2 post-fire years).

## Region and periods
- Affected area: the Sentinel-2 burned perimeter of `burn_severity` (whole fire, `perimetro_incendio2023_s2.gpkg`,
  13,770.9 ha) clipped to the park: region `afectada` of `zonas.gpkg`, 800.0 ha (644.6 ha after `where`).
- Control: ring of 1,500 m at 150 m from the Sentinel-2 perimeter (`herramientas/zonas.py`, geometries simplified to
  10 m), without the fire's envelope (unburned islands), the other 2023 patches with dNBR ≥ 0.1 and the 2018-2019
  changes (Cañada de los Guancheros fire), only in the park: region `control`, 2,052.6 ha (459.7 ha after `where`).
  Region in every call: `{"file": "<everest>/resultados/teide/zonas.gpkg",
  "name_field": "region", "within": {"wdpa_id": 389013}}`.
- `where` of the Sentinel-2 and Landsat series: `[{"variable": "ELEVATION", "sensor": "Copernicus", "min": 2007,
  "max": 2259}, {"variable": "NDVI", "sensor": "Sentinel-2", "period": ["2018-01-01", "2022-12-31"], "metric": "mean",
  "min": 0.15, "max": 0.443}]` (p5-p95 of the affected area; the NDVI condition removes lava flows and pumice).
  MODIS series: only the elevation condition.
- Periods: severity before 2023-05-15/08-14, after 2023-09-01/10-31 (dNBR) and 2024-05-15/08-14 (RdNBR, same
  season); series Sentinel-2 2017-04-01, Landsat 8/9 2013-04-01, MODIS 2001-01-01 (LAI 2003) to 2026-10-31; metrics
  with a 3-year reference (2020-09 to 2023-08).
- Sensors and why: Sentinel-2 (20 m, from 2017) for severity and the main series; Landsat 8/9 for LST and a second
  NDVI; MODIS for the long pre-fire trend (2001-2022) with mixed pixels; ERA5-Land for precipitation.

## Steps
1. (now) `image_count` of Sentinel-2 NDVI over the zones, 2017-04-01 to 2026-10-31, `"step": "monthly"` (winter snow,
   summit clouds). Not run in this case.
2. Severity of the whole fire and of the park (ids `bs_dnbr_fuego_s2`, `bs_dnbr_parque_s2`):
   ```json
   {"tool": "burn_severity", "args": {"region": {"bbox": [-16.68, 28.22, -16.28, 28.5]}, "start": "2023-05-15",
    "end": "2023-08-14", "other_start": "2023-09-01", "other_end": "2023-10-31", "sensor": "Sentinel-2",
    "perimeter": true}}
   ```
   Same with `"region": {"wdpa_id": 389013}`; with `"sensor": "Landsat"` (`bs_dnbr_parque_l8`); RdNBR with `"index":
   "RdNBR", "other_start": "2024-05-15", "other_end": "2024-08-14"` (`bs_rdnbr_{parque,fuego}_s2`); and over the
   perimeter, the envelope and `zonas.gpkg` with `"within": {"wdpa_id": 389013}` (`bs_*_perim_*`, `bs_*_env_*`,
   `bs_{d,rd}nbr_zonas_parque_s2`, these two with the `where` using 0.1505-0.4434). Method test: the same between
   summers 2018-06-01/09-30 and 2019-06-01/09-30 (`bs_dnbr_2019_parque_s2`). **Now**: `"largest": true` in the bbox
   call keeps only the fire's patch.
3. RdNBR offset: computed locally with the control's median RdNBR (0.153) on the GeoTIFF
   (`severidad_rdnbr_con_offset.py`). **Now**: give the unburned control as `offset_region` in the RdNBR call of
   `burn_severity` (e.g. the control of the GeoPackage that `control_ring` writes); it subtracts its median dNBR before
   the classes, the RBR and the RdNBR (the case subtracted the median RdNBR afterwards, so numbers may differ).
4. Independent products: `area_by_class` with `"collection": "MODIS/061/MCD64A1", "band": "BurnDate", "start":
   "2023-08-01", "end": "2023-09-30", "metric": "max", "breaks": [1]` over the park, the bbox and the envelope. The
   EMSR685 grading layer was downloaded by hand (`emsr685/`) and crossed with `region_stats` (`elev_emsr685_parque`).
   **Now**: use it directly as a region, `{"ems": "EMSR685", "within": {"wdpa_id": 389013}}` (grading product by
   default), e.g. in `region_stats` or as the affected area.
5. Matching: `region_stats` of ELEVATION over the perimeter, the envelope and the zones (`"scale": 10`, stats p5,
   p50, p95) and of NDVI Sentinel-2 2018-01-01/2022-12-31 (`"metric": "mean"`, `"scale": 20`) for the p5-p95 bounds.
   The ring was built with `herramientas/zonas.py`. **Now**:
   ```json
   {"tool": "control_ring", "args": {"region": {"file": "<everest>/resultados/teide/perimetro_incendio2023_s2.gpkg", "name_field": "region"},
    "gap": 150, "width": 1500, "exclude": {"file": "<one GeoPackage: envelope + other 2023 patches + 2018-2019 changes>"},
    "within": {"wdpa_id": 389013}}}
   ```
   then add the NDVI condition to the returned `where` (`control_ring` matches only elevation and/or slope).
6. Monthly series (ids `ts_<var>_<sensor>`): NDVI, LSWI, ALBEDO of Sentinel-2 (`"scale": 20`); NDVI, LST of Landsat
   (`"scale": 30`); NDVI (`"collection": "MODIS/061/MOD13Q1"`), ET and LAI of MODIS:
   ```json
   {"tool": "time_series", "args": {"region": {"file": "<everest>/resultados/teide/zonas.gpkg", "name_field": "region", "within": {"wdpa_id": 389013}},
    "variable": "NDVI", "sensor": "Sentinel-2", "start": "2017-04-01", "end": "2026-10-31", "step": "monthly",
    "where": <the where above>, "scale": 20}}
   ```
   Climate: `{"tool": "time_series", "args": {"region": {"wdpa_id": 389013}, "variable": "PRECIP", "sensor":
   "ERA5-Land", "start": "2001-01-01", "end": "2026-10-31", "step": "annual", "metric": "sum"}}`.
7. Seasonal curve: `compare_series` NDVI Sentinel-2 2017-09-01/2023-07-31 vs 2023-09-01/2026-08-31, monthly.
   Trends: `trend_table` annual NDVI Landsat 2013-2022, MODIS 2001-2022 and Sentinel-2 2024-01-01/2026-10-31.
8. Recovery metrics: `herramientas/metricas_recuperacion.py --evento 2023-08-15 --afectada afectada --control control`
   (3 reference years). **Now**:
   ```json
   {"tool": "recovery_metrics", "args": {"region": {"file": "<everest>/resultados/teide/zonas.gpkg", "name_field": "region", "within": {"wdpa_id": 389013}},
    "affected": "afectada", "control": "control", "variable": "NDVI", "sensor": "Sentinel-2",
    "start": "2017-04-01", "end": "2026-10-31", "event": "2023-08-15", "step": "monthly", "scale": 20,
    "reference_years": 3, "where": <the where above>}}
   ```
   or, shorter, `"region": {"ems": "EMSR685", "within": {"wdpa_id": 389013}}, "ring": true` (not equivalent: other
   perimeter, no NDVI matching). Repeat for LSWI, ALBEDO (Sentinel-2), NDVI, LST (Landsat), NDVI, LAI, ET (MODIS).
9. Not done on purpose: `trend_map` / `area_by_class` with `trend` and `recovery_map` of the post-fire period need
   ≥ 5 years; plan them for 2027-2028.

## Results to expect
From `estado/parques/teide.json` (`analisis`) and the files named:
- In the park: Sentinel-2 801.7 ha with dNBR ≥ 0.1 (perimeter 780.2 ha, 14 patches); Landsat 771.6 ha; MCD64A1
  827.4 ha; Sentinel-2 envelope 973.7 ha; EMSR685 906.0 ha (IoU with Sentinel-2 0.78); official 1,235 ha.
- Whole fire: Sentinel-2 patch 13,770.9 ha, envelope 14,820.4 ha (MITECO 14,750 ha; EMSR685 12,273.9 ha). Test 2019:
  51.5 ha vs 53 ha official for the Cañada de los Guancheros fire.
- dNBR classes in the park: low 387.3, moderate-low 309.6, moderate-high 72.8, high 0.1 ha. RdNBR median 0.99; high
  572.2 ha without offset, 500.6 ha (62.3 %) with the 0.153 offset (`severidad_rdnbr_con_offset.json`).
- NDVI Sentinel-2 (`metricas_NDVI_S2.json`): S95 0.127, −65.0 %, −15.95 MAD, DIT 0.54 years, no RRT; difference
  −32.55 MAD, 46.2 % recovered. Landsat NDVI: −43.53 MAD in the difference, 44.8 %.
- Difference, impact in MAD / % recovered: LSWI −47.37 / 86.2; ALBEDO −21.46 / 109.6 (RRT 1.3 years); LST Landsat
  +10.73 / 55.9; LAI −10.83 / 64.6; MODIS NDVI −40.5 / 62.6 (`metricas_*.json`). ET: ambiguous, left out.
- Pre-fire: MODIS NDVI difference already declining 2001-2022 (τ −0.39, p 0.013); first-year z of NDVI −19.5
  (Sentinel-2). ERA5-Land precipitation 183 mm in 2024, the lowest since 2001 (mean 2001-2022 318 ± 86 mm).

## Pitfalls
- The absolute dNBR underestimates severity in sparse shrubland on bright volcanic soil (low pre-fire NBR): use the
  RdNBR one year later, with the offset of a control, which matches the field severity (4.5-5/5).
- The official 1,235 ha seems to be the outer perimeter (with lava, pumice and islands); satellite and EMSR685 give
  less. Do not force the area to match; the GRAFCAN perimeter was not found.
- Coarse dNBR over a box catches seasonal change (4,150 ha of loose patches): use the perimeter's main patch.
- The drought of 2024 lowers the control too (19 months with |z| > 2): use the difference affected − control.
- The control is sparser broom (reference NDVI 0.19 vs 0.26) and has almost no pine: there is no unburned pine in that
  band of the park. Retama and pine are not separated (no vegetation map yet).
- Winter snow (Feb-Mar 2018) makes spikes in NDVI, LSWI and albedo. Recovery metrics are provisional (3.2 years).
- Restoration (fences, replanting, pine removal) is mixed with natural recovery. No MonitorEO warnings.

## Sources and citations
- Copernicus EMS EMSR685: https://mapping.emergency.copernicus.eu/activations/EMSR685 ; MITECO-OAPN, restoration of
  the park after the Arafo-Candelaria fire:
  https://www.miteco.gob.es/en/parques-nacionales-oapn/red-parques-nacionales/parques-nacionales/teide/restauracion-del-incendio-forestal-de-arafo.html ;
  Gobierno de Canarias: https://www.gobiernodecanarias.org/parquesnacionales/teide/conservacion/ ; AEMET Izaña:
  https://izana.aemet.es/impact-of-the-august-wildfire-in-tenerife-on-the-ciai-aemet-measurement-program/ ;
  Sánchez Cabañas (2024), TFG ULL: https://riull.ull.es/xmlui/handle/915/38490
- Recovery: Kyncl et al. (2006), doi:10.1007/s11258-006-9115-6; Bello-Rodríguez et al. (2020), doi:10.1002/eap.2206;
  Olano et al. (2017), doi:10.1016/j.biocon.2017.09.008; Cubas et al. (2022), doi:10.1016/j.jnc.2022.126263; Rozas et
  al. (2011), doi:10.1007/s00468-011-0564-8; Otto et al. (2009), doi:10.1007/s10342-009-0347-6; Méndez et al. (2015),
  doi:10.1007/s13595-015-0482-9; Pausas & Keeley (2017), doi:10.1016/j.tplants.2017.08.010; Zahabnazouri et al.
  (2025), doi:10.3390/s25103097; Vlassova et al. (2014), doi:10.3390/rs6076136; Rother et al. (2022),
  doi:10.1371/journal.pone.0274428.
- Method: Marcos et al. (2023), doi:10.1016/j.rse.2022.113441; Miller & Thode (2007), doi:10.1016/j.rse.2006.12.006;
  Veraverbeke et al. (2011), doi:10.1080/01431161003752430; Cansler & McKenzie (2012), doi:10.3390/rs4020456; Miller et
  al. (2016), doi:10.1016/j.foreco.2016.10.017; Fernandez-Manso et al. (2016), doi:10.1016/j.rse.2016.06.015.
- Cite MonitorEO (doi:10.5281/zenodo.23814894), Google Earth Engine (Gorelick et al. 2017,
  doi:10.1016/j.rse.2017.06.031) and the references and credits that each result returns (in `llamadas/<id>.json`),
  and the EMS credit line when EMSR685 is used.

## Files
Under <everest>/resultados/teide/: `llamadas.json` (35 calls), `llamadas/<id>.json`,
`monitoreo/`, `zonas.gpkg`, `perimetro_incendio2023_s2.gpkg`, `envolvente_incendio2023_s2.gpkg`, `zonas_in_*.gpkg`,
`emsr685/`, `severidad_rdnbr_con_offset.{py,json}`, `metricas_<VAR>_<sensor>.{json,png}`,
`mapa_severidad_dNBR_parque.png`. Viewer report draft: <everest>/visor/teide.yaml (id
`2026-11-everest-teide-incendio-2023`); publication to the site is not recorded in the park's json.
