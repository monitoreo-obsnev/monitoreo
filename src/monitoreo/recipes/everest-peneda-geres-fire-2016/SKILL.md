---
name: everest-peneda-geres-fire-2016
description: Wildfires of August 2016 in the Peneda sector (Arcos de Valdevez and Melgaço) of Peneda-Gerês National Park, in Atlantic heath, gorse and shrub with young oak woodland. ICNF official perimeters as regions, dating with daily Landsat 8 NBR and MCD64A1, dNBR and RdNBR severity with a control offset, strata by fire history (first fire vs reburned after 2010), a control ring without fires since 2006, and ten years of Landsat and MODIS series (NDVI, EVI, LAI, LSWI, ET, LST, albedo, NBR) with Marcos et al. (2023) recovery metrics and a BACI difference. Use it to repeat this case or to adapt it to a fire in fire-prone Atlantic shrubland with official perimeters and frequent reburning.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  park: Parque Nacional da Peneda-Gerês
  wdpa_id: "860"
  event: "peneda_geres_incendio_2016"
  event_date: "2016-08-09"
  disturbance: fire
  status: validated
  monitoreo_version: "0.3.86"
---

# August 2016 wildfires in the Peneda (Soajo–Gavieira), Peneda-Gerês

> **Files of this recipe.** `<everest>` is the folder of the EVEREST project where this case was computed: its
> zones (`resultados/<park>/*.gpkg`), its local scripts (`herramientas/`, `scripts/`) and its state files are not part of
> MonitorEO. To repeat the case, rebuild them with MonitorEO: the affected area from the official perimeter
> (`{"ems": ...}`, `{"effis_id": ...}`, `{"wfs": ...}`) or from `burn_severity` with `perimeter: true`, the control
> with `control_ring` (or `ring: true`), and the series and metrics with the calls marked «now». See
> `monitoreo-disturbance-case-study` for the method.

## Question
How severe were the two large fires of August 2016 inside the park and, ten years later, have carbon, water and
energy functions returned to their pre-fire level, and does it depend on the fire history (a first fire vs land that
had burned in 2010)? It informs post-fire management in a landscape that burns every ~11 years and gives a 10-year
trajectory to compare with the 2025 fire (estado/parques/peneda_geres.json).

## Region and periods
- Affected area: ICNF burned-area perimeters of 2016 (WFS `BDG:ardida_2016`): A (5,920.9 ha, 2,826 ha in the park) and
  B (1,506.3 ha, all in the park), downloaded to `resultados/peneda_geres/fuentes/icnf_wfs/` and clipped **locally**
  with the ICNF park limit (`BDG:rnap`) by `scripts/zonas_2016.py`. Regions of
  `<everest>/resultados/peneda_geres/zonas.gpkg` (field `region`): `afectada` (3,471.4 ha =
  A without the 857 ha burned in 2010, plus B, minus 18.8 ha reburned 2017–2025), strata `B` (1,506.3),
  `A_solo2016` (1,965.1), `A_requemado2010` (842.5), `A_sin_fuego_2006_2015` (381.4), and `control`.
- Control: ring 150–3150 m around the full A and B perimeters, inside the park, without anything burned according to
  the ICNF from 2006 to 2025 (150 m margin): 4,761.4 ha. No `within` in the calls: the zones are already clipped.
- where in all series (**W**): `[{"variable": "ELEVATION", "sensor": "Copernicus", "min": 604, "max": 1260}, {"landcover": "CORINE", "year": 2012, "exclude": ["water", "built", "cropland"]}]`
  (elevation p5–p95 of the affected zone; the control had 17 % cropland, excluded).
- Periods: severity pre 2016-05-01/07-31, post 2016-08-15/10-15; RdNBR post 2017-05-01/07-31 (same season, one year);
  series Landsat 8/9 2013-03-18 → 2026-11-26 (scale 60 m), MODIS 2000 → 2026-11-26 (LAI from 2002-07-04); reference
  for the metrics 2013-08/2016-07 (3 years). Event 2016-08-09 (B: 2016-08-11).
- Sensors: Landsat 8 for severity and the post-fire series (≈3.4 years of pre-fire reference); MODIS for the long
  reference and LAI, ET, LST, albedo; Landsat 5 only for the 1985–2011 trend; Sentinel-2 not used (starts 7 months after).

## Steps
Run with `herramientas/mcp_calls.py peneda_geres resultados/peneda_geres/llamadas.json` (27 calls). **Z** =
`{"file": "<everest>/resultados/peneda_geres/zonas.gpkg", "name_field": "region"}`.

0. «now», instead of the local download and clipping, the official perimeters as a region (not run; the 2016 polygons
   have no SGIF code, so select them by area and check that the result gives 2,826 + 1,506 ha in the park):
   `{"wfs": "https://si.icnf.pt/wfs/areas_ardidas", "layer": "BDG:ardida_2016", "cql_filter": "AreaHaSIG > 1500", "within": {"wdpa_id": 860}}`.
   «now» also `image_count` (Landsat, monthly, 2013-03-18 → 2016-07-31) to check the short pre-fire record.
1. Zone checks: `region_stats` of ELEVATION on Z (`"stats": ["mean", "min", "p5", "p50", "p95", "max"]`);
   `{"tool": "area_by_class", "args": {"region": Z, "landcover": "CORINE", "year": 2012}}`.
2. Date: MCD64A1 burn day and daily NBR:
   `{"tool": "region_stats", "args": {"region": Z, "collection": "MODIS/061/MCD64A1", "band": "BurnDate", "start": "2016-01-01", "end": "2016-12-31", "metric": "min", "stats": ["min", "p5", "p50", "p95", "max"]}}`
   `{"tool": "time_series", "args": {"region": Z, "variable": "NBR", "sensor": "Landsat", "start": "2016-05-01", "end": "2016-11-30", "step": "daily", "scale": 30}}`
3. Severity and contrast with the official area:
   `{"tool": "burn_severity", "args": {"region": {"bbox": [-8.45, 41.82, -8.15, 42.05]}, "sensor": "Landsat", "start": "2016-05-01", "end": "2016-07-31", "other_start": "2016-08-15", "other_end": "2016-10-15", "perimeter": true}}`,
   the same on `{"wdpa_id": 860}` and, without `perimeter`, on Z; RdNBR on Z with `"index": "RdNBR", "other_start": "2017-05-01", "other_end": "2017-07-31"`.
   The control offset and hectares per zone were computed **locally** (`scripts/dnbr_por_zona.py` on the GeoTIFFs).
   «now»: add `"offset_region"` = a region with the control alone (e.g. a GeoPackage with only the `control`
   polygon; not created yet) so the dNBR, RBR and RdNBR classes come already corrected by the control median.
4. Monthly series (Landsat at 60 m: NDVI, LSWI, LST, ALBEDO, NBR; MODIS: NDVI and EVI of MOD13Q1 every 16 days, LST
   MOD11A1, ALBEDO MCD43A3, ET MOD16A2, LAI MCD15A3H, monthly):
   `{"tool": "time_series", "args": {"region": Z, "variable": "NDVI", "sensor": "Landsat", "start": "2013-03-18", "end": "2026-11-26", "step": "monthly", "scale": 60, "where": W}}`
   `{"tool": "time_series", "args": {"region": Z, "variable": "NDVI", "sensor": "Modis", "collection": "MODIS/061/MOD13Q1", "start": "2000-02-18", "end": "2026-11-26", "step": "16-day", "where": W}}`
5. Reference dynamics: `compare_series` monthly 2013-03-18/2016-07-31 vs 2016-09-01/2026-11-26 (NDVI, LSWI Landsat;
   NDVI MODIS from 2011); `trend_table` annual NDVI MODIS 2001–2015 and 2017–2025 with `"test": "hamed-rao"`, Landsat
   2017–2025 and Landsat 5 1985–2011; per pixel:
   `{"tool": "area_by_class", "args": {"region": Z, "variable": "NDVI", "sensor": "Landsat", "trend": true, "start": "2017-01-01", "end": "2025-12-31", "step": "annual", "where": W}}`
6. Recovery metrics: **local** `herramientas/metricas_recuperacion.py` (`scripts/metricas_todas.sh`, event 2016-08-09,
   for `afectada` and each stratum against `control`; table `tabla_metricas_2016.csv`). «now», one call per variable and stratum:
   `{"tool": "recovery_metrics", "args": {"region": {"file": "<everest>/resultados/peneda_geres/zonas.gpkg", "name_field": "region"}, "affected": "B", "control": "control", "variable": "NDVI", "sensor": "Modis", "collection": "MODIS/061/MOD13Q1", "start": "2013-08-01", "end": "2026-11-26", "event": "2016-08-09", "step": "16-day", "reference_years": 3, "where": W}}`
   (`"reference_years": 10` with MODIS is possible but A burned in 2006 and 2010: keep 3 or use B only); `recovery_map`
   (Landsat summer, 60 m) on B to see where it has not recovered.

## Results to expect
From estado/parques/peneda_geres.json, `severidad_dnbr_por_zona.txt`, `severidad_rdnbr_por_zona.txt` and `tabla_metricas_2016.csv`:
- Date: NBR drop between 2016-08-06 (A 0.369) and 2016-08-15 (−0.030); B 0.295 (2016-07-30) → −0.069; control
  0.347 → 0.266. MCD64A1 in the affected zone: 184 pixels, days 217–234, median 223 (A 222, B 224).
- Area: 98.3 % of A and 93.8 % of B with dNBR ≥ 0.1; in the park 4,175 ha vs 4,332 ha of the ICNF (−3.6 %; A −2.2 %,
  B −6.2 %); whole park dNBR ≥ 0.27: 5,043 ha vs 5,473 ha burned in 2016 (−7.9 %).
- Severity (affected, with control offset 0.0413): median dNBR 0.447; 310 ha unburned, 668 low, 954 moderate-low,
  1,081 moderate-high, 454 high. RdNBR (offset 0.0374): 1,296 low, 1,504 moderate, 320 high; medians B 0.424,
  A_solo2016 0.326, A_requemado2010 0.295.
- Recovery (affected / difference with control): NDVI MODIS RRT 4.84 / 6.66 years (103.3 % / 94.8 % recovered);
  NDVI Landsat 4.81 / 5.23; LSWI 4.89 / 4.89; EVI 2.92 / 3.32; LAI 3.31 / 6.06; LST Landsat 1.4 / 1.14; albedo MODIS
  RET of the difference 8.23 years, 85.3 % recovered. Impact of the difference: NBR −26.73 MAD, EVI −21.35, ET −19.87, NDVI MODIS −18.45.
- Strata (difference): B does not return for NDVI (88.7 % MODIS, 93.7 % Landsat) or EVI (78.1 %); A_solo2016 NDVI
  RRT 4.84 (MODIS); A_requemado2010 3.23 (MODIS) and 2.81 (Landsat).
- Post-fire NDVI trend 2017–2025 (Landsat): +0.022/year in the affected zone (p < 0.001), +0.0044 control (p = 0.06);
  80.2 % of the affected pixels with a significant increase vs 30.9 % of the control.

## Pitfalls
- dNBR ≥ 0.1 without correction picks up the summer drying of pastures and heath (18,005 ha in the park; 853 ha «low»
  in the unburned control): correct by the control median (`offset_region` now) or use ≥ 0.27.
- A is not a clean stratum: 2,445 of its 2,826 ha in the park had burned in 2006–2015; the reburned stratum seems to
  recover faster because its reference was already depressed (legacy). B (no fire since before 2006) is the reference
  for a first fire.
- Short Landsat 8 reference (3.4 years); the LSWI z is useless (control down to −22.1) and its relative impact is
  meaningless (reference ≈ 0). MODIS LST is 1 km and ET 500 m (RRT 0.06 years of the difference is noise).
- 2017 was hot and dry and the control also dropped (NDVI −8 to −13 %): read the difference. Hansen shows delayed tree
  mortality in 2017, which delays the inflection (DIT 1.1–1.3 years with MODIS NDVI).
- Marcos et al. (2023) studied 2005 fires with MODIS, not these; only its abstract was read.

## Sources and citations
- ICNF burned areas (WFS): https://si.icnf.pt/wfs/areas_ardidas?version=2.0.0&request=GetCapabilities ; natural
  disaster order of 2016-08-31 (copy by the Câmara Municipal de Montalegre):
  https://www.cm-montalegre.pt/cmmontalegre/uploads/writer_file/document/1681/incndios_-_repos-160921154454.pdf
- Independent products: MCD64A1, doi:10.5067/MODIS/MCD64A1.061; Hansen Global Forest Change, doi:10.1126/science.1244693.
- Method: Marcos et al. 2023, doi:10.1016/j.rse.2022.113441; Marcos et al. 2021, doi:10.3390/rs13040780; Miller &
  Thode 2007, doi:10.1016/j.rse.2006.12.006; Fernández-García et al. 2018, doi:10.1016/j.rse.2017.12.029; Veraverbeke
  et al. 2011, doi:10.1080/01431161003752430; Gouveia et al. 2010, doi:10.5194/nhess-10-673-2010; Lhermitte et al. 2011,
  doi:10.1016/j.isprsjprs.2010.08.004; Ryu et al. 2018, doi:10.3390/rs10060918.
- Ecology: Fernández-Guisuraga et al. 2022, doi:10.3390/f13020145; Meneses et al. 2021, doi:10.3390/fire4040076;
  Oliveira & Fernandes 2023, doi:10.3390/fire6050210.
- Cite MonitorEO (doi:10.5281/zenodo.23814894), Google Earth Engine (doi:10.1016/j.rse.2017.06.031) and the references
  and credits that each result returns (`referencias_monitoreo` and `creditos` of the park json).

## Files
- `<everest>/resultados/peneda_geres/`: `llamadas.json`, `llamadas/`, `monitoreo/`,
  `zonas.gpkg`, `metricas_<VAR>_<sensor>[_<stratum>].json/png`, `tabla_metricas_2016.csv`, `severidad_*_por_zona.txt`,
  `mapa_severidad_dnbr_2016.png`, `scripts/`, `fuentes/` (ICNF WFS layers, DGT, EFFIS, official documents).
- State: `estado/parques/peneda_geres.json`; report `informe_perturbaciones.html`. Not published in the viewer (not recorded).
- Pending: full text of Marcos et al. (2023); EFDA Portugal (1,507 MB, awaiting permission); split by cover and
  severity class; compare with the 2025 fire from 2028.
