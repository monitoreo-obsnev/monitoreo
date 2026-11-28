---
name: everest-c19-amortiguacion-termica-sierra-nevada
description: Thermal buffering of the land surface by vegetation in Sierra Nevada (Spain), by day and by night. Land surface temperature (LST) of eight land covers of the Spanish Forest Map 1:50,000 (dense and open pine plantations, Pyrenean oak, holm oak, shrubland, pasture-shrub, grassland, bare ground), matched by 200 m elevation band and aspect - Landsat 8/9 by day, ECOSTRESS by night (LST_NIGHT), and daily MODIS Terra/Aqua day and night LST in 1 km cells homogeneous by cover - with snow screening (MOD10A1), extremes, cover-vs-open slopes (De Frenne et al. 2019), AEMET heatwave days, z anomalies, altitudinal transects and a modelled air temperature reference (HighResClimNevada, WRF 1 km). Use it to repeat this case or to map thermal refugia of any land cover against open ground in a mountain area.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  park: Sierra Nevada National Park and Natural Park
  wdpa_id: "389011 (National Park); 555588878 (SAC/SPA Sierra Nevada = National + Natural Park)"
  event: "C19 (EVEREST case study)"
  event_date: "2003-2025 (July-August and December-February)"
  disturbance: other
  status: validated
  monitoreo_version: "0.3.98 (Landsat, ECOSTRESS, transects, MOD10A1 snow); 0.3.100 (MODIS LST series and anomalies, recomputed 2026-11-28)"
---

# Thermal buffering by vegetation in Sierra Nevada: day and night land surface temperature by cover, 2003-2025

> **Versions of MonitorEO.** Computed with MonitorEO 0.3.98, before 0.3.99. Since 0.3.99 a variable of MODIS of the
> catalog is reduced, at its resolution, on the sinusoidal grid of its products (not on pixels of 250-1000 m of the
> UTM zone; data given by collection and band are not); the LST of MODIS has a snow filter on by default (`quality:
> {"snow": false}` for the LST as it was): a repetition gives slightly different MODIS values. The overpass of MODIS
> Terra drifts earlier since 2022 (in 2025 about 9.8 h by day and 20.8-20.9 h by night, local solar time, instead of
> about 11 h and 22 h): trends of its LST that include 2022 or later lean cooler by day and warmer at night; compare
> them with those up to 2021, and check the bands Day_view_time and Night_view_time.
>
> **Recomputation with MonitorEO 0.3.100 (2026-11-28):** the 8 MODIS calls of steps 5 and 8 (and the Terra daytime holm-oak check) were repeated with the
> same arguments in `<everest>/resultados/casos/C19/recalculo_0_3_100/` (default `quality`, so with the new snow
> filter). Results to expect below give both versions (0.3.98 → 0.3.100).

> **Files of this recipe.** `<everest>` is the folder of the EVEREST project where this case was computed.
> The cover zones (`resultados/casos/C19/zonas/*.gpkg`), the local scripts
> (`resultados/casos/C19/scripts/`), the Spanish Forest Map (MITECO), the AEMET heatwave list and HighResClimNevada are
> not part of MonitorEO; the scripts rebuild the zones from the public files. Everything else is the MonitorEO calls
> below, which can be repeated as they are.

## Question
How much do forests (pine plantations, Pyrenean oak, holm oak) and shrubland cool by day and warm by night compared
with pasture and bare ground at the same elevation and aspect, and how much do they buffer the extremes (hottest days,
coldest nights) along the elevation gradient? It informs which covers and densities to keep or restore as thermal
refugia (thinning and naturalisation of pine plantations, oak woods, high-mountain shrubland on exposed south slopes)
and where to monitor extreme heat. **The satellite measures the surface (canopy, soil), not the air under the canopy.**

## Region and periods
- Covers: Spanish Forest Map 1:50,000 (MFE50, MITECO) of Granada (18) and Almería (04), clipped to the SAC/SPA
  Sierra Nevada (WDPA 555588878 = National + Natural Park) and grouped (`scripts/zonas_cubiertas.py`): `pinar_denso`
  (pine plantations and conifer mixtures with tree canopy cover TFCCARB ≥ 60 %), `pinar_claro` (TFCCARB < 60 %),
  `robledal` (Melojares), `encinar`, `matorral`, `pastizal_matorral`, `herbazal` (+ Prado), `suelo_desnudo` («Monte sin
  vegetación superior»). Region: `C = {"file": "<everest>/resultados/casos/C19/zonas/cubiertas_mfe50.gpkg",
  "name_field": "cubierta"}`.
- Homogeneous MODIS cells (`scripts/celdas_modis.py`, needs the 90 m DEM of step 2): the MOD11A1 sinusoidal grid
  (926.625 m), cells ≥ 95 % inside the park with ≥ 75 % of one cover, with mean elevation (200 m band) and the aspect of
  the mean slope (N 315-45°, E, S 135-225°, W; the strata are named with O, oeste, for W). 105 strata `cover|band|aspect` from 1,200 to 2,800 m:
  `E = {"file": ".../zonas/estratos_modis.gpkg", "name_field": "estrato"}`. Pair file for anomalies:
  `P = {"file": ".../zonas/pares_1600_2000.gpkg", "name_field": "cubierta"}` (dense pine and pasture-shrub cells of
  1,600-2,000 m).
- Matching: by 200 m elevation band (`zones` of ELEVATION) and aspect (`where` on ASPECT; north = two calls, 0-45 and
  315-360, summed weighting by pixels, because `where` conditions are AND-ed). In MODIS, the open reference is
  `pastizal_matorral` (no homogeneous grassland or bare-ground cells at forest elevations).
- Periods and sensors: summer = July-August; winter = December-February. Landsat 8/9 only (2013-2025, ~10:50 h, no
  harmonize); ECOSTRESS LST_NIGHT 2018-07-09 to 2025 (70 m, 22-04 h); MODIS 2003-2025: Aqua day (MYD11A1, ~13:30 h),
  Terra night (MOD11A1, ~22:30 h) and Aqua night (MYD11A1, ~01:30 h); MOD10A1 `NDSI_Snow_Cover` to keep only snow-free
  winter days (< 10 in both cells compared).

## Steps
All calls are in `<everest>/resultados/casos/C19/llamadas.json` (ids in brackets), run with `herramientas/mcp_calls.py`.
`Z = {"wdpa_id": 555588878}`; `S = ["07-01", "08-31"]`; `W = ["12-01", "02-28"]`;
`ZON = {"variable": "ELEVATION", "sensor": "Copernicus", "breaks": [1000, 1200, ..., 3200]}` (every 200 m).

1. Check the images (annual step) [`ic_landsat_verano`, `ic_landsat_invierno`, `ic_myd_dia_verano`,
   `ic_mod_noche_verano`, `ic_myd_noche_invierno`, `ic_eco_noche_verano`, `ic_eco_noche_invierno`], e.g.:
   ```json
   {"tool": "image_count", "args": {"region": Z, "variable": "LST_NIGHT", "sensor": "ECOSTRESS",
    "start": "2018-07-01", "end": "2025-08-31", "step": "annual", "season": S}}
   ```
2. DEM for the MODIS cells [`dem90`]:
   `{"tool": "download_image", "args": {"region": Z, "variable": "ELEVATION", "sensor": "Copernicus", "resolution": 90, "crs": "EPSG:25830"}}`
3. Check the covers against Earth Engine layers [`rs_treecover`, `rs_canopy`, `rs_elev`]:
   `{"tool": "region_stats", "args": {"region": C, "variable": "TREE_COVER", "sensor": "Hansen"}}` (also
   `CANOPY_HEIGHT`/`ETH` and `ELEVATION`/`Copernicus`).
4. Landsat day and ECOSTRESS night by cover × elevation band × aspect (12 calls: `rs_ls_ver_*`, `rs_ls_inv_*`,
   `rs_eco_ver_*`, `rs_eco_inv_*`, each with `_S` 135-225, `_N1` 0-45, `_N2` 315-360):
   ```json
   {"tool": "region_stats", "args": {"region": C, "variable": "LST", "sensor": "Landsat",
    "start": "2013-07-01", "end": "2025-08-31", "season": S, "metric": "mean", "stats": ["mean", "p50", "std"],
    "zones": ZON, "where": [{"variable": "ASPECT", "sensor": "Copernicus", "min": 135, "max": 225}]}}
   ```
   Winter: `"start": "2013-12-01", "end": "2025-02-28", "season": W`. ECOSTRESS: `"variable": "LST_NIGHT", "sensor":
   "ECOSTRESS"`, 2018-07-01 (data from 2018-07-09) to 2025-08-31, and 2018-12-01 to 2025-02-28.
5. Daily MODIS series of the homogeneous strata (6 calls, 3.5-7 min each) [`ts_myd_dia_ver`, `ts_mod_noche_ver`,
   `ts_myd_noche_ver`, `ts_myd_dia_inv`, `ts_mod_noche_inv`, `ts_myd_noche_inv`]:
   ```json
   {"tool": "time_series", "args": {"region": E, "variable": "LST_NIGHT", "sensor": "Modis",
    "collection": "MODIS/061/MOD11A1", "start": "2003-07-01", "end": "2025-08-31", "season": S,
    "step": "daily", "metric": "mean", "stat": "mean"}}
   ```
   Day: `"variable": "LST", "collection": "MODIS/061/MYD11A1"`; Aqua night: `LST_NIGHT` with `MODIS/061/MYD11A1`;
   winter: `"start": "2003-12-01", "end": "2025-02-28", "season": W`.
6. Snow of the strata in winter [`ts_nieve_inv`]:
   `{"tool": "time_series", "args": {"region": E, "collection": "MODIS/061/MOD10A1", "band": "NDSI_Snow_Cover", "unit": "%", "start": "2003-12-01", "end": "2025-02-28", "season": W, "step": "daily", "metric": "mean", "stat": "mean"}}`
7. Altitudinal transects (4 calls) [`tr_ls_dia_norte`, `tr_eco_noche_norte`, `tr_ls_dia_sur`, `tr_eco_noche_sur`]:
   north face `[[-3.4425, 37.1323], [-3.3667, 37.0563]]` (to the Veleta), south face
   `[[-3.33, 36.96], [-3.3114, 37.0533]]` (to the Mulhacén):
   `{"tool": "transect", "args": {"line": L, "variable": "LST", "sensor": "Landsat", "start": "2013-07-01", "end": "2025-08-31", "season": S, "metric": "mean", "spacing": 150}}`
   (night: `LST_NIGHT`, `ECOSTRESS`, from 2018-07-09).
8. z anomalies of dense pine and pasture-shrub [`an_myd_dia_ver`, `an_mod_noche_ver`]:
   `{"tool": "anomalies", "args": {"region": P, "variable": "LST", "sensor": "Modis", "collection": "MODIS/061/MYD11A1", "start": "2003-07-01", "end": "2025-08-31", "season": S, "step": "16-day", "threshold": 1.5}}`
   (`step: "daily"` is refused: only monthly, 16-day or annual).
9. Local analysis (`scripts/olas_aemet.py`, `scripts/aire_wrf.py`, `scripts/analisis.py`): ΔLST = cover − open in each
   band and aspect (≥ 100 Landsat pixels or ≥ 20 ECOSTRESS pixels of each); for MODIS, per day and matched stratum:
   mean Δ, Δ on the days with open LST ≥ p95 of its stratum (summer) or ≤ p5 (snow-free winter), slope of the cover
   anomaly on the open anomaly within strata (< 1 = buffering), Δ on AEMET heatwave days in Granada, day − night
   amplitude (Aqua 13:30 − 01:30); and against the air of HighResClimNevada (each MODIS cell → nearest WRF cell):
   LST − tasmax/tasmin, slope LST ~ air, and offsets on tasmax ≥ p95 / tasmin ≤ p5 days.

## Results to expect
- Covers vs Earth Engine layers: Hansen tree cover mean 67 % in dense pine, 30 % open pine, 33 % oak, 30 % holm oak,
  1-6 % in grassland, pasture-shrub and bare ground; ETH canopy height 14.6 m dense pine, 15.6 m oak
  (`llamadas/rs_treecover.json`, `rs_canopy.json`).
- Landsat summer, Δ vs pasture-shrub: dense pine −6.24 °C (−8.0 to −3.9 by band; 15 strata), open pine −3.77, oak −5.15,
  holm oak −1.71, shrubland −1.72; vs grassland, dense pine −7.36. Winter (snow-free): dense pine −3.29, open pine −2.44
  (`tablas/delta_landsat_ecostress_resumen.csv`).
- ECOSTRESS night, Δ vs pasture-shrub: dense pine +0.91 °C (summer), +1.25 °C (winter); open pine +0.61 / +0.83; oak
  −0.43 / −0.25; the night warming grows with elevation (≈ 0 at 1,000-1,200 m, +1 to +2 °C at 1,600-2,200 m)
  (`tablas/delta_landsat_ecostress_*.csv`).
- MODIS homogeneous cells vs pasture-shrub: Aqua 13:30 summer, dense pine −2.18 °C mean, −3.50 °C on the hottest days,
  slope 0.73; on AEMET heatwave days −2.02 vs −2.20 on the rest. Coldest snow-free winter nights: dense pine +1.65
  (Terra) / +2.00 °C (Aqua); oak −0.66 / −0.97 (`tablas/delta_modis_celdas.csv`, 0.3.98).
  Recomputation with MonitorEO 0.3.100 (2026-11-28) (`recalculo_0_3_100/tablas/delta_modis_celdas.csv`, native MODIS grid): dense pine −2.54 °C mean,
  −3.98 °C on the hottest days, slope 0.70; heatwave days −2.35 vs −2.56; open pine −1.41 (was −0.85); oak −1.73
  (was −1.20); holm oak +0.52 (was +0.96); night (Terra / Aqua) dense pine +1.16 / +1.43, oak −0.46 / −0.74 (was
  −0.98 / −0.99); coldest snow-free winter nights dense pine +1.61 / +2.24, oak −0.24 / −0.71. Fewer paired days (one
  pixel per cell: dense pine summer day 14,885 → 13,962 stratum-days).
- Summer day − night amplitude (Aqua, 1,400-2,200 m): dense pine 20.1 °C, open pine 19.9, pasture-shrub 23.4,
  grassland 24.9 (`tablas/amplitud_dia_noche_modis_1400_2200.csv`). Recomputation with MonitorEO 0.3.100 (2026-11-28): 20.0, 19.7, 23.7, 25.1.
- Against HighResClimNevada air (1,600-2,200 m): LST − tasmax on the hottest air days +7.0 °C dense pine vs +9.3 °C
  pasture-shrub; on the coldest winter nights LST − tasmin +3.6 vs +1.1 °C; slopes LST ~ tasmax 0.37-0.61 with no clear
  order by cover (`tablas/lst_frente_aire_wrf.csv`). Recomputation with MonitorEO 0.3.100 (2026-11-28): +7.0 vs +9.6 °C by day, +3.6 vs +1.4 °C on the
  coldest winter nights, slopes 0.62 (dense pine) and 0.49 (pasture-shrub).
- Holm oak − pasture-shrub in the 10 verification strata, summer 2013-2025 (`verificacion_encinar/delta.py`): MODIS Aqua
  +0.85 → +0.44 °C, Terra +0.46 → +0.10 °C (Recomputation with MonitorEO 0.3.100 (2026-11-28)), Landsat −1.30 °C in the same cells.
- z anomalies (16-day): practically unchanged with 0.3.100 (2015-07-01: z 2.02 pasture-shrub, 2.19 dense pine).
- Image counts: Landsat ~4 valid observations per pixel per season; ECOSTRESS night median 1.8 per pixel per summer
  (2 summers without data) (`llamadas/ic_*.json`).

## Pitfalls

- MODIS series over the «homogeneous» cells were sampled at 1000 m, not on the native 926.6 m sinusoidal grid: each
  cell got 2-3 values a day, including neighbouring pixels. The holm oak came out +0.96 °C (Aqua 13:30) and +0.46 °C
  (Terra 10:30) warmer than pasture-shrubland with MODIS, but −1.30 °C cooler with Landsat inside the same cells
  (files in `verificacion_encinar/`). Trust Landsat for open covers; check `n_pixels` per cell before trusting MODIS cells.
  Recomputation with MonitorEO 0.3.100 (2026-11-28): with the native grid (`n_pixels` = number of cells) the holm oak goes from +0.96 to +0.52 °C (Aqua, 2003-2025, all strata); in the
  2013-2025 check of 10 strata, Aqua +0.85 → +0.44 °C and Terra +0.46 → +0.10 °C, but is still not cooler as with Landsat: pixel mixing explained part of the discrepancy, not all of it (open
  canopy seen at 1 km, viewing geometry in steep terrain, few reference cells: not checked). Keep Landsat for the holm oak.
- `where` conditions are AND-ed: a north aspect (315-45°) needs two calls (0-45 and 315-360).
- MODIS 1 km mixes covers: build homogeneous cells on the sinusoidal grid locally; at forest elevations only
  pasture-shrub is available as open reference in MODIS (homogeneous grassland and bare ground are above 2,400 m).
- MODIS LST had no snow filter before 0.3.99 (now on by default): the winter days were screened with MOD10A1
  `NDSI_Snow_Cover` in both cells compared, which the pairing still needs. Recomputation with MonitorEO 0.3.100 (2026-11-28): the built-in filter (same-day
  MOD10A1/MYD10A1, NDSI_Snow_Cover ≥ 35 in any 500 m pixel) is looser than the case's own (< 10 in both cells): keep both.
- MODIS Terra overpass drifts in the last years: night z anomalies of 2022-2025 are partly an artefact; prefer
  same-day cover − open differences.
- The ETH canopy height gives 5-7 m on bare rock and grassland at high elevation (model artefact).
- HighResClimNevada: some cells are fill values (mask values outside −60…60 °C); its yearly TXx is 3-4 °C below the
  yearly maximum of its daily tasmax in the same cell (unexplained), so extremes are defined from the daily values.
- The AEMET province list (Zenodo, 2024 update) has one 2016 heatwave whose end precedes its start: drop it.
- `anomalies` refuses `step: "daily"`.
- Landsat transect on the south face has no summer values above ~2,580 m (snow/clouds filtered).

## Sources and citations
- De Frenne et al. (2019), Nat. Ecol. Evol., https://doi.org/10.1038/s41559-019-0842-1; Li et al. (2015), Nat.
  Commun., https://doi.org/10.1038/ncomms7603; Xu et al. (2022), Sci. Adv., https://doi.org/10.1126/sciadv.abo0119;
  Zellweger et al. (2019), Trends Ecol. Evol., https://doi.org/10.1016/j.tree.2018.12.012; John et al.
  (2024), Environ. Res. Commun.,
  https://doi.org/10.1088/2515-7620/ad7705 (all verified with scite verify_papers, 2026-11-28).
- HighResClimNevada: García-Valdecasas Ojeda et al. (2025), ESSD 17, 2809-2829,
  https://doi.org/10.5194/essd-17-2809-2025; data https://doi.org/10.5281/zenodo.14883471 (CC BY 4.0).
- AEMET (2024). Olas de calor en España desde 1975. https://doi.org/10.5281/zenodo.18005738.
- MITECO, Mapa Forestal de España 1:50.000:
  https://www.miteco.gob.es/es/biodiversidad/servicios/banco-datos-naturaleza/informacion-disponible/mfe50_descargas_andalucia.html
- Cite MonitorEO (https://doi.org/10.5281/zenodo.23814894), Google Earth Engine (Gorelick et al. 2017,
  https://doi.org/10.1016/j.rse.2017.06.031) and the references and credits that each result returns (Landsat C2 L2,
  MOD11A1/MYD11A1 v061, ECOSTRESS L2T LSTE v002, Copernicus DEM, Hansen GFC, ETH canopy height, WDPA).

## Files
`<everest>/resultados/casos/C19/`: `informe.md` (report, in Spanish), `estado.json`,
`llamadas.json`, `llamadas/` (responses and figures), `recalculo_0_3_100/` (MODIS recomputed with 0.3.100: calls,
responses, adapted `analisis.py`, `comparar.py`, tables and old-vs-new comparisons), `monitoreo/` (CSV, PNG, README), `zonas/`, `scripts/`, `tablas/`,
`fuentes/` (MFE50, AEMET PDFs, ORIGEN.txt).
