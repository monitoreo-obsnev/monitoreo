---
name: everest-c20-vegetacion-clima-local-sierra-nevada
description: Biophysical effect of the vegetation of Sierra Nevada (Spain) on the local surface climate - daytime and night land surface temperature, evapotranspiration and latent heat, albedo, LAI and vegetation water (LSWI and MSI of Sentinel-2 and Landsat) - by land cover (Spanish Forest Map) in paired elevation-aspect strata of pure MODIS cells against open pasture-shrubland, seasonal cycle and dry vs wet years, with WRF forcing covariates and the 2005 Lanjaron fire as a before-after control-impact test of losing a pine forest. Use it to repeat this case or to measure the cooling service of forests vs open land in another mountain.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  park: Sierra Nevada National Park
  wdpa_id: "389011"
  event: "C20 (and sierra_nevada_incendio_2005)"
  event_date: "2003-2025 (fire 2005-09-22)"
  disturbance: other
  status: validated
  monitoreo_version: "0.3.98"
---

# Effect of vegetation on the local surface climate, Sierra Nevada, 2003-2025

> **Versions of MonitorEO.** Computed with MonitorEO 0.3.98, before 0.3.99. Since 0.3.99 a variable of MODIS of the
> catalog is reduced, at its resolution, on the sinusoidal grid of its products (not on pixels of 250-1000 m of the
> UTM zone; data given by collection and band are not); the LST of MODIS has a snow filter on by default (`quality:
> {"snow": false}` for the LST as it was); the ALBEDO of MODIS (MCD43A3) keeps the magnitude inversions, so it has
> values over snow: a repetition gives slightly different MODIS values.

> **Files of this recipe.** `<everest>` is the folder of the EVEREST project
> where this case was computed: its zones (`resultados/casos/C20/zonas/*.gpkg`, copied from case C19), its local
> scripts (`resultados/casos/C20/scripts/`) and the WRF files are not part of MonitorEO. To repeat the case elsewhere,
> rebuild the strata from a land-cover map (one polygon per cover|elevation band|aspect, made of pure MODIS cells),
> and use `ring` with an official fire perimeter for the before-after test.

## Question
How much does each vegetation type cool (or warm) the land surface, and by which mechanism (latent heat or albedo)?
Does it keep more water in the vegetation (LSWI, MSI)? How does it change with season, elevation and dry years, and
what happened when the pine forest burned (Lanjaron, 2005)? It informs the valuation of the climate-regulation service
of forests, shrublands and pastures (naturalization of pine plantations, post-fire restoration). The case was
limited to: no precipitation; vegetation water only from Sentinel-2 or Landsat (no ERA5-Land, SMAP or TerraClimate VPD/SOILM);
TerraClimate AET, PET and CWD only to split dry and wet years.

## Region and periods
- Strata: `{"file": "<everest>/resultados/casos/C20/zonas/estratos_modis.gpkg", "name_field": "estrato"}`: 105
  strata `cover|band|aspect` (8 covers of the Mapa Forestal de España 1:50,000 inside WDPA 555588878: dense pine
  (canopy cover ≥ 60 %), open pine, Pyrenean oak, holm oak, shrubland, pasture-shrubland, grassland, bare; 200 m
  bands 1,200-2,600 m; aspect N/E/S/W), each a union of MODIS 1 km cells with ≥ 75 % of one cover (C19
  `scripts/celdas_modis.py`). Reference of each comparison: pasture-shrubland of the same band and aspect (69 pairs).
- Pair: `{"file": "<everest>/resultados/casos/C20/zonas/pares_1600_2000.gpkg", "name_field": "cubierta"}`: dense pine
  (67 cells, 5,751 ha) and pasture-shrubland (50 cells, 4,291 ha) at 1,600-2,000 m.
- Fire: the official perimeter `{"file": "<everest>/resultados/lanjaron_fire_perimeter/lanjaron_fire_perimeter.shp"}`
  (read only) with `"ring": {"gap": 200, "width": 2000}` and the CORINE 2000 condition of
  `everest-sierra-nevada-fire-2005`.
- Periods: MODIS 2003-2025 (Aqua LST from 2002-07); seasons summer 06-01/08-31, winter 12-01/02-28, spring
  03-01/05-31; Sentinel-2 2017-2025; Landsat 8/9 2013-2025 (no sensor jump); fire: MODIS from 2000 (5 reference years),
  Landsat harmonized from 1995 (10 reference years).
- Sensors and why: MODIS for the energy balance (ET/LE MOD16A2GF, ALBEDO MCD43A3, LST/LST_NIGHT MYD11A1 at 13:30 and
  01:30, LAI MCD15A3H) because only MODIS has ET and daily LST over 20 years; Sentinel-2 (20 m) and Landsat (30 m) for
  vegetation water.

## Steps
All calls are in `<everest>/resultados/casos/C20/llamadas.json` (made by `scripts/llamadas.py`). `PARES`, `ESTR` and
`FUEGO` are the regions above; `CORINE` = `[{"landcover": "CORINE", "year": 2000, "exclude": ["water", "built", "cropland", "bare"]}]`.

1. Images (`ic_*`):
   ```json
   {"tool": "image_count", "args": {"region": PARES, "variable": "ALBEDO", "sensor": "Modis", "start": "2003-12-01",
    "end": "2025-02-28", "step": "annual", "season": ["12-01", "02-28"]}}
   ```
   Also ET, LAI (annual 2003-2025), ALBEDO summer, LSWI Sentinel-2 summer and spring and LSWI Landsat summer over
   `{"wdpa_id": 389011}` with `"scale": 100`.
2. Energy balance per stratum and season (`rs_{et,alb,lstd}_{ver,inv,pri}`, `rs_{lstn,lai}_{ver,inv}`):
   ```json
   {"tool": "region_stats", "args": {"region": ESTR, "variable": "LST", "sensor": "Modis",
    "collection": "MODIS/061/MYD11A1", "start": "2003-06-01", "end": "2025-08-31", "season": ["06-01", "08-31"],
    "metric": "mean", "stats": ["mean", "p50", "std"]}}
   ```
   Same for ET, ALBEDO, LAI (no collection) and LST_NIGHT (MYD11A1).
3. Vegetation water per stratum (`rs_lswi_s2_ver`, `rs_lswi_s2_pri`, `rs_msi_s2_ver`, `rs_lswi_ls_ver`):
   ```json
   {"tool": "region_stats", "args": {"region": ESTR, "variable": "LSWI", "sensor": "Sentinel-2", "start": "2017-06-01",
    "end": "2025-08-31", "season": ["06-01", "08-31"], "metric": "mean", "stats": ["mean", "p50", "std"], "scale": 20}}
   ```
   MSI Sentinel-2 the same; LSWI Landsat 2013-06-01/2025-08-31 with `"scale": 30`; spring 2018-03-01/2025-05-31.
4. Monthly series of the pair (`ts_et`, `ts_le`, `ts_albedo`, `ts_lst_dia`, `ts_lst_noche`, `ts_lai`, `ts_lswi_ls`,
   `ts_lswi_s2`, `ts_msi_s2`):
   ```json
   {"tool": "time_series", "args": {"region": PARES, "variable": "LE", "sensor": "Modis", "start": "2003-01-01",
    "end": "2025-12-31", "step": "monthly"}}
   ```
5. Dry and wet years (`ts_cwd`, `ts_aet`, `ts_pet`):
   ```json
   {"tool": "time_series", "args": {"region": {"wdpa_id": 389011}, "variable": "CWD", "sensor": "TerraClimate",
    "start": "2003-01-01", "end": "2024-12-31", "step": "annual", "metric": "sum"}}
   ```
6. Fire BACI (`rec_et`, `rec_albedo`, `rec_lst_dia`, `rec_lst_noche`, `rec_lswi_ls`):
   ```json
   {"tool": "recovery_metrics", "args": {"region": FUEGO, "ring": {"gap": 200, "width": 2000}, "variable": "ET",
    "sensor": "Modis", "start": "2000-01-01", "end": "2025-12-31", "event": "2005-09-22", "step": "monthly",
    "reference_years": 5, "where": CORINE}}
   ```
   LSWI Landsat: `"start": "1995-01-01", "reference_years": 10, "scale": 60, "quality": {"water": false, "harmonize": true}`
   (took 20 minutes). Sentinel-2 after the fire (`ts_fuego_lswi_s2`, `ts_fuego_msi_s2`): `time_series` with the same
   region, `ring` and `where`, 2017-04-01/2025-12-31, `"scale": 20, "quality": {"water": false}`.
7. Trends of the pair (`tr_et`, `tr_lst_dia`, `tr_albedo`): `trend_table` annual 2003-2025, `"test": "hamed-rao"`.
8. Local: `scripts/wrf_covariables.py` (HighResClimNevada WRF 1 km: net radiation, wind, tasmax, tasmin, DTR at the
   nearest WRF cell of each MODIS cell, 2003-2022), `scripts/analisis.py` (differences against pasture-shrubland of the
   same band and aspect, regression ΔLST ~ ΔET + Δalbedo (+ WRF), monthly cycle, dry/wet terciles of CWD, local
   Mann-Kendall/Sen of the difference), `scripts/figuras.py`.

## Results to expect
From `resultados/casos/C20/tablas/resumen.json` unless stated:
- Dense pine − pasture-shrubland (median of 15 strata): daytime LST −2.65 °C in summer, −2.98 spring, −0.61 winter;
  night LST +1.14 °C summer; ET +1.84 kg m-2 8d-1; albedo −0.021; LAI +0.62; LSWI Sentinel-2 +0.188 (Landsat
  +0.195); MSI −0.296. Open pine −1.27 °C; oak −1.45 °C (winter +2.40); holm oak +1.20 °C with MODIS (not reliable: Landsat in the same cells gives −1.30 °C; see Pitfalls); shrubland +0.15 °C.
- Summer means: LSWI Sentinel-2 0.214 dense pine vs 0.044 pasture-shrubland; LST 34.0 vs 35.8 °C.
- Regression over 69 paired strata: ΔLST_summer = −0.35 − 0.17·ΔET + 50.8·Δalbedo, R² 0.20 (with WRF covariates
  R² 0.29); Δalbedo acts as a proxy of canopy density (r −0.40 with ΔLAI). ΔLSWI ~ ΔET r 0.71.
- Pair 1,600-2,000 m (`tablas/par_climatologia_mensual.csv`): ΔLST day −0.9 (Dec) to −3.5 °C (Sep), night +1.1 to
  +1.7 °C, ΔLE +4.5 to +12.4 W m-2 Mar-Oct, Δalbedo −0.017 to −0.026, ΔLSWI 0.16 (Jun) to 0.36 (Jan, Landsat).
- Dry (CWD ≥ 603 mm) vs wet (≤ 532 mm) years: ΔLST summer −3.21 vs −3.00 °C; ΔET +2.14 vs +2.49.
- Trends of the difference 2003-2025: ΔLAI −0.0041/yr (p 0.044); ΔLST summer +0.021 °C/yr (p 0.072).
- WRF (`tablas/wrf_pares.csv`): summer net radiation 195.6 (pine cells) vs 170.9 W m-2; wind 2.8 vs 3.2 m s-1.
- Fire, affected − control (`llamadas/rec_*.json`): daytime LST +0.21 → +2.01 °C (2006) → +0.83 (2024), 12.7 MAD,
  83.2 % recovered; ET +0.85 → −0.59 → −0.47 (−19.9 MAD); albedo −0.001 → +0.019 (2007) → +0.011 (+16.4 MAD);
  night LST +0.50 → +0.15 °C; LSWI Landsat +0.050 → −0.069 → −0.015 (−18.3 MAD, 63 % recovered, RET 10.5 years);
  Sentinel-2 2017-2025 LSWI −0.013 (summer), −0.028 (autumn).

## Pitfalls

- MODIS series over the C19 cells were sampled at 1000 m, not on the native 926.6 m grid (500 m for ET, albedo and
  LAI), so each cell mixes neighbouring pixels. The holm oak came out warmer than pasture-shrubland with MODIS and
  cooler with Landsat in the same cells (−1.30 °C): trust Landsat for open, patchy covers. Check `n_pixels` per cell
  per day before trusting «homogeneous» MODIS cells.
- With MonitorEO 0.3.98, MCD43A3 with its quality filter kept almost only snow-free pixels (winter albedo 0.10-0.16; in some winters
  only 21 % of the pasture had data), so the snow-albedo warming of clearings could not be measured; since 0.3.99
  `ALBEDO` keeps the magnitude inversions and has values over snow.
- The albedo coefficient of the cross-sectional regression has the non-radiative sign (darker → cooler): albedo is
  confounded with canopy density; the fire (brighter after burning, yet warmer) is the cleaner test.
- `trend_table` annual LST uses the mean of the clear-sky images of the year, biased to summer (27-29 °C in the
  pasture): its trend (−0.13 °C/yr, p 0.014) contradicts the mean of monthly means (+0.06 °C/yr): use seasonal trends or
  the monthly series.
- MOD16 ET/LE is a model at 500 m (gap-filled MOD16A2GF): compare covers only. LST is surface, not air, temperature.
- WRF (HighResClimNevada) simulates its own vegetation (Noah-MP): use it as forcing covariate, not as the effect; its
  air temperature is 1.3 °C higher over the pine cells (80 m lower).
- Grassland, shrubland and bare strata are few and high (2,000-2,600 m), where the pasture reference is scarce.
- MSI and LSWI use the same bands (LSWI = (1 − MSI)/(1 + MSI)).
- The Landsat LSWI `recovery_metrics` (1995-2025, monthly, 60 m) took 20 minutes; the rest of the calls, 4-200 s.

## Sources and citations
- Li et al. (2015), doi:10.1038/ncomms7603; Alkama & Cescatti (2016), doi:10.1126/science.aac8083; Bright et al.
  (2017), doi:10.1038/nclimate3250; Duveiller et al. (2018), doi:10.1038/s41467-017-02810-8; Mu et al. (2011),
  doi:10.1016/j.rse.2011.02.019; Ellison et al. (2017), doi:10.1016/j.gloenvcha.2017.01.002; Marcos et al. (2023),
  doi:10.1016/j.rse.2022.113441; Hunt & Rock (1989), doi:10.1016/0034-4257(89)90046-1; Xiao et al. (2004),
  doi:10.1016/j.rse.2004.03.010 (all verified with scite verify_papers, 2026-11-28).
- HighResClimNevada: García-Valdecasas Ojeda et al. (2025), doi:10.5194/essd-17-2809-2025; data
  doi:10.5281/zenodo.14883471 (CC BY 4.0).
- Mapa Forestal de España 1:50,000 (MITECO); official perimeter of the 2005 Lanjaron fire (see
  `everest-sierra-nevada-fire-2005`).
- Cite MonitorEO (doi:10.5281/zenodo.23814894), Google Earth Engine (Gorelick et al. 2017,
  doi:10.1016/j.rse.2017.06.031) and the references and credits that each result returns (collected in
  `tablas/referencias_monitoreo.json`).

## Files
Under <everest>/resultados/casos/C20/: `informe.md`, `estado.json`, `llamadas.json`
(46 calls; 49 run), `llamadas/<id>.json`, `monitoreo/`, `zonas/` (from C19), `scripts/`, `tablas/` (resumen.json,
estratos_*.csv, delta_por_cubierta.csv, par_*.csv, wrf_*.csv, fig_*.png). Not published in the viewer.
