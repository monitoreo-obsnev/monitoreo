---
name: everest-c12-procesionaria-defoliacion-invernal
description: Winter defoliation by the pine processionary moth (Thaumetopoea pityocampa) in the pine forests of Sierra Nevada and Sierra de las Nieves National Parks (Andalusia, Spain). Monthly MODIS, Landsat and Sentinel-2 NDVI (also CLre, NBR, LSWI) per monitoring stand, the autumn-to-late-winter drop as a robust z against each stand's own history, validated with the official COPLAS infestation degree (0-5, 1993-2015, GBIF), a BACI of the 2011-12 outbreak with recovery_metrics, winter difference maps with compare_map and download_comparison, and winter cold (ERA5-Land TMIN) and summer drought (TerraClimate CWD) to separate other causes. Use it to repeat this case or to adapt it to a winter-feeding defoliator in evergreen conifers with stand-level field data.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  park: Sierra Nevada National Park; Sierra de las Nieves National Park
  wdpa_id: "389011; 555700945"
  event: "C12 (EVEREST case study); outbreak used for the BACI: winter 2011-12, Sierra Nevada"
  event_date: "every winter 2001-2026 (October-November to February-March); outbreak 2011-12 (COPLAS campaign 2012)"
  disturbance: pest
  status: partial
  monitoreo_version: "0.3.98"
---

# Pine processionary moth winter defoliation, Sierra Nevada and Sierra de las Nieves, 2001-2026

> **Versions of MonitorEO.** Computed with MonitorEO 0.3.98, before 0.3.99. Since 0.3.99 a variable of MODIS of the
> catalog is reduced, at its resolution, on the sinusoidal grid of its products (not on pixels of 250-1000 m of the
> UTM zone; data given by collection and band are not): a repetition gives slightly different MODIS values.

> **Files of this recipe.** `<everest>` is the folder of the EVEREST project where this case was computed; this case is in
> `<everest>/resultados/casos/C12/`. Its stands (`rodales_coplas.gpkg`), zones (`zonas_brote2012.gpkg`,
> `pinar_coplas_*.gpkg`) and scripts (`scripts/`) are not part of MonitorEO. To repeat it, download the COPLAS
> Darwin Core archive (step 1) and rebuild them with the scripts, or use any stand polygons with field data of
> defoliation. See `monitoreo-disturbance-case-study` for the general method.

## Question
Can the winter defoliation by the pine processionary moth be mapped every winter with Sentinel-2, Landsat and MODIS,
separated from drought, to decide which stands to treat (Bt kurstaki, pheromone traps) and to check whether the
treatments work? Status «partial»: validated against the official field survey for MODIS 2001-2015 only; the
Sentinel-2 part (2018-2026) is NOT calibrated (no open field data after 2015) and treatments were not assessed.

## Region and periods
- Stands (affected and unaffected): COPLAS monitoring stands (Junta de Andalucía) with at least half of their area
  inside the WDPA polygon of each park: 171 in Sierra Nevada (22,888 ha) and 24 in Sierra de las Nieves (9,566 ha),
  `{"file": "<everest>/resultados/casos/C12/rodales_coplas.gpkg", "name_field": "rodal"}` (`scripts/rodales_coplas.py`
  from the COPLAS archive and the WDPA polygons). They are also the pine mask (better than CORINE «trees», which
  includes oak woodland).
- Outbreak BACI: affected = 34 Sierra Nevada stands with degree ≥ 4 in 2012 (5,531 ha); control = 22 stands with
  degree 0 in 2012 and ≤ 1 in 2011 (2,243 ha), `{"file": ".../zonas_brote2012.gpkg", "name_field": "region"}`
  (`scripts/zonas_brote.py`). The control is lower and sparser (NDVI 0.43 vs 0.61): an imperfect control.
- Periods: winter Y = October-November of Y-1 → February-March of Y; spring May-June of Y; summer July-August.
  COPLAS degree of campaign Y is assessed «from end of winter to beginning of spring», so it belongs to winter Y
  (confirmed: best correlation with winter Y, `tablas/modis_ndvi_desfase.txt`).
- Sensors: MODIS MOD13Q1 (250 m, 2000-) is the validated one; Landsat 5/7 (2003-2016, scale 60 to save quota;
  `harmonize`, `landsat7`; no Landsat 2012-05-05 to 2013-03-18); Sentinel-2 L2A (2017-04-, scale 30 for stand series,
  20 m GeoTIFF). `quality {"snow_ndsi": 0.4}` for Sentinel-2 and Landsat; MonitorEO refuses it for MODIS.

## Steps
1. Field data (outside MonitorEO): COPLAS Darwin Core archive, `https://ipt.gbif.es/archive.do?r=coplas` (35 MB, CC BY
   4.0, DOI 10.15470/s1mxjb): `event.txt` (stand polygon in `footprintWKT`, `eventDate` = campaign year),
   `extendedmeasurementorfact.txt` (degree 0-5). WDPA polygons from Earth Engine (`WCMC/WDPA/current/polygons`,
   `SITE_ID`). Then `scripts/rodales_coplas.py <case dir>`.
2. Check the images (ids `ic_s2_sn`, `ic_s2_sdln`):
   ```json
   {"tool": "image_count", "args": {"region": {"wdpa_id": 389011}, "variable": "NDVI", "sensor": "Sentinel-2",
    "start": "2017-10-01", "end": "2026-06-30", "step": "monthly", "quality": {"snow_ndsi": 0.4}, "scale": 100,
    "where": [{"landcover": "CORINE", "year": 2018, "exclude": ["water", "grassland", "wetland", "cropland",
    "shrubland", "built", "bare", "snow"]}]}}
   ```
3. Monthly series per stand (one call per sensor and index; 4-6 min for MODIS and Sentinel-2, ~30 min for Landsat):
   ```json
   {"tool": "time_series", "args": {"region": {"file": ".../rodales_coplas.gpkg", "name_field": "rodal"},
    "variable": "NDVI", "sensor": "Modis", "start": "2000-03-01", "end": "2026-06-30", "step": "monthly",
    "metric": "median", "stat": "mean"}}
   ```
   Same with `"sensor": "Sentinel-2"`, `"start": "2017-04-01"`, `"quality": {"snow_ndsi": 0.4}`, `"scale": 30` for
   NDVI, CLre, NBR and LSWI (ids `ts_s2_*_rodales`), and with `"sensor": "Landsat"`, `"start": "2003-01-01"`,
   `"end": "2016-06-30"`, `"quality": {"snow_ndsi": 0.4, "harmonize": true, "landsat7": true}`, `"scale": 60` for
   NDVI and LSWI (ids `ts_landsat_*_rodales`). Do not run Landsat 1993-2016 at 30 m over 195 stands in one call: it ran
   > 30 min and was cancelled.
4. Winter drop per stand and winter (`scripts/caida_invernal.py <dir> <csv> <tag>`): drop = mean Feb-Mar(Y) − mean
   Oct-Nov(Y-1); spring = May-Jun(Y) − Oct-Nov(Y-1); summer = Jul-Aug(Y) − May-Jun(Y); anomaly = (drop − stand median)
   / (1.4826 × stand MAD). Validation with COPLAS: `scripts/validacion.py`, `scripts/desfase.py`,
   `scripts/umbrales.py`.
5. Outbreak BACI (ids `rm_modis_ndvi_brote2012`, `rm_landsat_ndvi_brote2012`):
   ```json
   {"tool": "recovery_metrics", "args": {"region": {"file": ".../zonas_brote2012.gpkg", "name_field": "region"},
    "affected": "afectada", "control": "control", "variable": "NDVI", "sensor": "Modis", "start": "2002-01-01",
    "end": "2016-12-31", "event": "2011-12-01", "step": "monthly", "reference_years": 5}}
   ```
   **Now**, with treated stands: `pairs` of [treated, untreated] stands, one BACI each, to measure the treatments.
6. Climate per park (ids `ts_cwd_sn`, `ts_cwd_sdln`, `ts_tmin_sn`, `ts_tmin_sdln`): `time_series` of `CWD`
   (TerraClimate) and `TMIN` (ERA5-Land), `{"wdpa_id": ...}`, monthly, 2000-2025/2026; `scripts/clima.py`. Do not use
   a file with many features sharing the same `name_field` as the region (it failed when drawing the chart).
7. Winter maps (ids `cm_*`, `dc_s2_ndvi_sn_inv2026`):
   ```json
   {"tool": "download_comparison", "args": {"region": {"file": ".../pinar_coplas_sierra_nevada.gpkg",
    "name_field": "region"}, "variable": "NDVI", "sensor": "Sentinel-2", "start": "2025-10-01", "end": "2025-11-30",
    "other_start": "2026-02-01", "other_end": "2026-03-31", "metric": "median", "vmin": -0.15, "vmax": 0.15,
    "resolution": 20, "crs": "EPSG:25830", "quality": {"snow_ndsi": 0.4}}}
   ```
   `compare_map` with the same arguments (no resolution/crs) for previews; spring check with `other_start/other_end`
   = May-June. Summary by class and by stand: `scripts/tif_invierno.py <dir> <tif> <tag> sierra_nevada` (GDAL).
   **Now**: `compare_map` / `download_comparison` with `"z": true` and a multi-year reference may give the per-pixel
   anomaly directly (not tested here).

## Results to expect
- MODIS, 2001-2015, n = 2,386 stand-winters: Spearman anomaly vs COPLAS degree −0.177; AUC degree ≥ 3 vs ≤ 1 = 0.659
  (≥ 4: 0.685); median anomaly by degree 0…5: +0.016, −0.065, −0.391, −0.597, −0.736, −1.609
  (`tablas/modis_ndvi_validacion.json`, `tablas/modis_ndvi_auc_extra.txt`). Sierra Nevada AUC 0.669; Sierra de las
  Nieves 0.58 (p = 0.12, not significant).
- Threshold anomaly ≤ −1.5: sensitivity 0.242, specificity 0.902, 24.0 % of alerts with degree ≥ 3 (prevalence 11.9 %)
  (`tablas/modis_ndvi_umbrales.csv`).
- Within-winter correlation in Sierra Nevada: 2012 −0.39, 2011 −0.28, 2004 0.01
  (`tablas/modis_ndvi_spearman_por_anio_sn.txt`).
- Spring recovery unrelated to degree (ρ = −0.013, p = 0.51).
- Landsat NDVI 2004-2015 (scale 60): AUC 0.626, ρ = −0.105 (`tablas/landsat_ndvi_validacion.json`): worse than MODIS.
  Landsat LSWI (≈ NDII): AUC 0.544, ρ = −0.014 (p = 0.54): no signal (`tablas/landsat_lswi_validacion.json`).
- BACI 2011-12, MODIS: difference impact −6.0 MAD, z min −2.68, tINF 2012-02, RRT 1.42 years, 91.6 % recovered;
  Landsat: −3.45 MAD, z min −1.17 (`llamadas/rm_*_brote2012.json`). Half of the MODIS difference comes from the control
  rising (+9.8 %) while the affected stands fell (−8.8 %).
- Sierra Nevada: colder winters, larger drop of the whole pine forest (TMIN Dec-Feb vs mean drop ρ = 0.47, p = 0.016);
  Sierra de las Nieves: drier previous summer, lower mean COPLAS degree (ρ = −0.77, p = 0.0007, 15 years)
  (`tablas/clima_correlaciones.txt`).
- Sentinel-2 2018-2026: NDVI vs CLre anomaly ρ = 0.89, NBR vs LSWI 0.87, NDVI vs LSWI −0.05, with MODIS 0.14-0.24
  (`tablas/acuerdo_indices_2018_2026.csv`). Winter 2025-26, Sierra Nevada, 23,720 ha: 1,232.7 ha with NDVI drop
  ≤ −0.15 and 1,451.8 ha between −0.15 and −0.10 (`tablas/s2_ndvi_sn_inv2026_clases.csv`).

## Pitfalls
- Winter weather (snow, cold, low sun) moves the whole park together: compare each stand with its own history, not
  with the park. Subtracting the park mean of the winter made it worse (AUC 0.602).
- The Sentinel-2 SWIR indices (LSWI, NBR) behave differently from NDVI/CLre in winter (snow residue, wet soil); the
  literature favours MSI/NDII with Landsat, but here they could not be calibrated for Sentinel-2.
- `quality {"snow_ndsi": ...}` is refused for MODIS; a MODIS call with it fails at once.
- Landsat per-stand series over 195 polygons are slow (~31 min for 2003-2016 at 60 m); MODIS takes ~4 min.
- TerraClimate had no 2025 data in Earth Engine (empty months): drop those years.
- MODIS series were run with MonitorEO 0.3.98, which sampled MODIS on a 250 m UTM grid instead of its native sinusoidal
  grid: small stands mix neighbouring pixels. The AUC falls with stand size (0.696 with ≥ 35 MODIS pixels, 0.551,
  not significant, with < 20; reviewer's check on `tablas/modis_ndvi_rodal_anio.csv`); rerun with ≥ 0.3.99 and keep
  to large stands. The pooled signal also leans on outbreak years (AUC 0.593 without 2011-2012).
- Pooled stand-winter p-values ignore repeated stands and shared winters: treat them as indicative only.
- COPLAS is a visual 0-5 score per stand, revisited by a technician only for degree ≥ 3; it ends in 2015 in GBIF.

## Sources and citations
- COPLAS: Ros-Candeira et al. (2019) ZooKeys 852:125-136, https://doi.org/10.3897/zookeys.852.28567; dataset DOI
  10.15470/s1mxjb.
- Hódar, Castro & Zamora (2003) https://doi.org/10.1016/S0006-3207(02)00183-0; Otsu et al. (2018)
  https://doi.org/10.3390/s18103278; Pérez-Romero et al. (2019) https://doi.org/10.3390/rs11141736; Gazol et al. (2019)
  https://doi.org/10.3389/fevo.2019.00458; Marcos et al. (2023) https://doi.org/10.1016/j.rse.2022.113441 (all verified
  with scite on 2026-11-28).
- Cite MonitorEO (https://doi.org/10.5281/zenodo.23814894), Google Earth Engine (Gorelick et al. 2017,
  https://doi.org/10.1016/j.rse.2017.06.031) and the references and credits that each result returns (MODIS MOD13Q1,
  Sentinel-2 L2A, Landsat Collection 2, ERA5-Land, TerraClimate, CORINE, WDPA).

## Files
`<everest>/resultados/casos/C12/`: `informe.md` (report), `estado.json`,
`llamadas.json` and `llamadas/` (calls and answers), `monitoreo/` (CSV, PNG, GeoTIFF with README), `tablas/`
(derived tables), `figuras/`, `scripts/`, `fuentes/` (COPLAS archive and `ORIGEN.txt`), `rodales_coplas.gpkg`,
`rodales_coplas_grados.csv`, `zonas_brote2012.gpkg`, `pinar_coplas_*.gpkg`. Not published in the results viewer.
