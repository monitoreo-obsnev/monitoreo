---
name: everest-c11-pinares-aclareos-sequia
description: Drought response of thinned versus unthinned pine stands and a satellite search for broadleaf understorey under pine plantations in Sierra Nevada and Sierra de Guadarrama National Parks (Spain). Treated stands from the European Forest Disturbance Atlas (harvest 1995-2011, canopy kept), elevation- and aspect-matched untreated controls, summer BACI with recovery_metrics pairs for the 2012, 2017 and 2022 droughts (NDVI, LSWI, MSI, TCW of Landsat and Sentinel-2), SPEI12, and the seasonal NDVI amplitude of Sentinel-2 against distance to broadleaf forest. Use it to repeat this case, or to compare treated and untreated stands (thinning, fencing, restoration) without an official treatment map. Partial results, no official map of thinnings with date and intensity; the thinned stands are a proxy from the European Forest Disturbance Atlas.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  park: Parque Nacional de Sierra Nevada; Parque Nacional de la Sierra de Guadarrama
  wdpa_id: "389011; 555546231"
  event: "C11 (EVEREST case study)"
  event_date: "droughts 2012-06-01, 2017-06-01, 2022-06-01; treatments 1995-2011"
  disturbance: drought
  status: partial
  monitoreo_version: "0.3.96"
---

# Thinning, drought and naturalisation of pine plantations, Sierra Nevada and Guadarrama, 2012–2025

> **Files of this recipe.** `<everest>` is the folder of the EVEREST project where this case was computed: its
> zones (`resultados/casos/C11/zonas/*.gpkg`), its local scripts (`resultados/casos/C11/scripts/`) and its state files
> are not part of MonitorEO. To repeat the case, rebuild the zones with the scripts (they need the EFDA rasters and the
> layers of step 1), then run the calls of `resultados/casos/C11/llamadas.json`. See `monitoreo-disturbance-case-study`
> for the BACI method.

## Question
Do thinned (or naturalised, pine–broadleaf) stands resist and recover better from drought than dense pine, and where
is there broadleaf regeneration under the pines that would justify a diversification thinning or enrichment planting?
It informs where to invest in thinning, where in enrichment, and where not to intervene.

## Region and periods
- Treated area: no official treatment map was available (Junta de Andalucía/REDIAM download server not usable from
  the computer of the case; no open layer with date and intensity). Proxy built **locally**: pine (CORINE 2018 class 312) inside
  the National Park and the EFDA v2.1.1 forest mask, with EFDA aggregated agent = 3 (harvest) and last disturbance in
  1995–2011, and ETH canopy height ≥ 5 m in 2020 (thinning or partial cut, not an unregenerated clear-cut).
  `scripts/recorte_efda.py` clips the EFDA Spain rasters (Zenodo record 13333034) to the 30 m EPSG:3035 grid of the
  park DEM; `scripts/zonas_tratamientos.py` builds the zones.
- Control: pine of the same layers with no EFDA disturbance in 1985–2023, > 30 m from any disturbed pixel, canopy ≥ 5 m,
  sampled in 3×3-pixel blocks stratified by 100 m elevation band and 4 aspect classes to match the treated area (up to
  3× its area per stratum). Region **Z**: `{"file": "<everest>/resultados/casos/C11/zonas/zonas.gpkg", "name_field": "region"}`
  with features `tratado_sn`, `control_sn`, `tratado_gu`, `control_gu`. No `where` is needed (matching is in the zones).
- Naturalisation zones **N**: `{"file": "<everest>/resultados/casos/C11/zonas/zonas_natural.gpkg", "name_field": "region"}`
  (`pinar_mixto_*`: top quintile of seasonal NDVI amplitude; `pinar_puro_*`: bottom quintile; 182 ha each, matched by
  elevation and aspect; `scripts/naturalizacion.py`).
- Periods: droughts 2012, 2017 and 2022 (SPEI12 minima below −1.8 in both parks), reference 3 years; summer
  June–September for the interpreted BACI.
- Sensors: Landsat (2012 with `landsat7` and `harmonize`; 2017 Landsat 8/9 only), Sentinel-2 for 2022 and for the
  naturalisation layers; SPEIbase for drought. MODIS not used (stands of a few hectares).

## Steps
All calls ran with `herramientas/mcp_calls.py casos/C11 resultados/casos/C11/llamadas.json` (27 calls).

1. Base layers per park (P = `{"wdpa_id": 389011}` or `{"wdpa_id": 555546231}`):
   `{"tool": "download_image", "args": {"region": P, "variable": "ELEVATION", "sensor": "Copernicus", "resolution": 30, "crs": "EPSG:3035"}}`,
   `{"tool": "download_image", "args": {"region": P, "image": "COPERNICUS/CORINE/V20/100m/2018", "band": "landcover", "unit": "1", "resolution": 30, "crs": "EPSG:3035"}}`,
   `{"tool": "download_image", "args": {"region": P, "variable": "CANOPY_HEIGHT", "sensor": "ETH", "resolution": 30, "crs": "EPSG:3035"}}`
   (CANOPY_HEIGHT needs `"sensor": "ETH"`). Then the local scripts of the zones.
2. Check the images:
   `{"tool": "image_count", "args": {"region": Z, "variable": "NDVI", "sensor": "Sentinel-2", "start": "2018-01-01", "end": "2025-12-31", "step": "monthly"}}` and
   `{"tool": "image_count", "args": {"region": Z, "variable": "NDVI", "sensor": "Landsat", "start": "2007-01-01", "end": "2025-12-31", "step": "annual", "season": ["05-01", "10-31"], "quality": {"landsat7": true}}}`.
3. Drought index per park: `{"tool": "time_series", "args": {"region": P, "variable": "SPEI12", "sensor": "SPEIbase", "start": "2005-01-01", "end": "2024-12-31", "step": "monthly"}}`
   (not over Z: its scattered polygons hold no 0.5° pixel centre).
4. Summer BACI, one call per drought and variable, both parks at once with `pairs`:
   `{"tool": "recovery_metrics", "args": {"region": Z, "pairs": [["tratado_sn", "control_sn"], ["tratado_gu", "control_gu"]], "variable": "NDVI", "sensor": "Landsat", "start": "2013-04-01", "end": "2025-12-31", "event": "2017-06-01", "step": "annual", "season": ["06-01", "09-30"], "reference_years": 3, "min_coverage": 0.5}}`
   and the same with `"variable": "LSWI"`; for 2012 `"start": "2007-01-01", "end": "2016-12-31", "event": "2012-06-01", "quality": {"landsat7": true, "harmonize": true}`;
   for 2022 `"sensor": "Sentinel-2", "start": "2018-06-01", "end": "2025-12-31", "event": "2022-06-01"` with NDVI, LSWI and MSI.
   Monthly versions (no `season`) were run as a contrast for 2012 (NDVI, TCW; `landsat7` only) and 2017 (NDVI, LSWI):
   about 11 minutes each.
5. Naturalisation layers per park:
   `{"tool": "download_image", "args": {"region": P, "variable": "NDVI", "sensor": "Sentinel-2", "start": "2019-01-01", "end": "2025-12-31", "season": ["06-15", "07-31"], "metric": "median", "resolution": 30, "crs": "EPSG:3035"}}`
   and the same with `"season": ["03-01", "04-30"]`; then `scripts/naturalizacion.py` (amplitude, distance to CORINE
   311/313 with GDAL proximity, tables by distance, canopy height and elevation, heuristic classes, N zones) and
   `scripts/naturalizacion_residuo.py` (amplitude without the elevation effect).
6. Naturalised vs pure pine BACI: as step 4 with region N and
   `"pairs": [["pinar_mixto_sn", "pinar_puro_sn"], ["pinar_mixto_gu", "pinar_puro_gu"]]` (NDVI Landsat 2017; NDVI and
   LSWI Sentinel-2 2022; annual summer).
7. `scripts/resumen_baci.py` (all metrics into `resumen_baci.csv`) and `scripts/referencias.py`.

## Results to expect
- Zones (`zonas/resumen_zonas.json`): treated 214.1 ha (SN) and 630.4 ha (GU); control 648.8 and 1,859.0 ha; elevation
  p50 1,822/1,827 m and 1,767/1,760 m.
- Summer NDVI difference treated − control, reference median: −0.0451 (SN 2009–2012), −0.0418 (SN 2014–2017),
  −0.0350 and −0.0273 (GU); Sen slope of the difference after 2017: +0.0018 per year (SN, p = 0.035) and +0.0008
  (GU, p = 0.009); LSWI +0.0014 (SN, p = 0.035) and +0.0015 (GU, p = 0.019) (`llamadas/rec2017_*_verano.json`).
- First-summer impact, SN: NDVI 2012 −4.1 % treated vs −5.3 % control; NDVI 2017 −3.5 % vs −5.3 %; LSWI 2017 −1.0 % vs
  −4.7 %. GU: NDVI 2012 +1.5 % vs +2.4 %, 2017 +4.4 % vs +3.9 %, 2022 (Sentinel-2) −2.1 % vs −1.5 % (`resumen_baci.csv`).
- SPEI12 minima: SN −2.05 (2012), −1.94 (2017), −2.07 (2022), −2.60 (2023), −2.94 (2024); GU −2.27 (2012), −2.53
  (2017), −1.78 (2022) (`spei12_anual.json`).
- Seasonal NDVI amplitude of pine, p50: −0.006 (SN), 0.025 (GU); broadleaf CORINE 311: −0.025 (SN), 0.194 (GU).
  Spearman with elevation 0.443 (SN); with distance to broadleaf −0.157 (SN), −0.017 (GU); without the elevation
  effect −0.070 and 0.026 (`naturalizacion.json`, `naturalizacion_residuo.json`).

## Pitfalls
- `recovery_metrics` rejects `season` with a monthly step: use annual with the season, or monthly without it.
- Monthly Landsat series over 2007–2016 crossing 2013 without `harmonize` show a sensor jump, and winter snow makes the
  monthly difference noisy; interpret the annual summer series.
- Treated stands are still converging with the control after the cut: with 3 reference years, part of that trend is
  read as a smaller drought impact. `impact_mad` of annual differences is huge (MAD of 3 values ≈ 0): do not use it.
- SPEI12 over the scattered zone polygons returns no pixels (0.5°): use the park.
- In Sierra Nevada the seasonal NDVI amplitude follows elevation and slope (north face negative, south face positive),
  not the understorey; holm oak (evergreen) gives no signal. The heuristic classes need field validation.
- Treated stands are fragmented (median patch 0.36 ha in SN, 0.45 ha in GU) on the 30 m EPSG:3035 grid, while Landsat
  and Sentinel-2 are sampled on their UTM grids: edge pixels mix neighbouring untreated pine (the 90 m control blocks
  have far fewer edges), which dampens the treated − control difference. Prefer larger, compact treated patches.
- EFDA agent codes used: 2 fire, 3 harvest, 4 mixed (checked against the 2005 Lanjarón fire, 12,938 fire pixels).

## Sources and citations
- Viana-Soto & Senf 2025 (EFDA), doi:10.5194/essd-17-2373-2025; Marcos et al. 2023, doi:10.1016/j.rse.2022.113441;
  Sohn et al. 2016, doi:10.1016/j.foreco.2016.07.046; Gómez-Aparicio et al. 2009, doi:10.1890/08-1656.1;
  Navarro-Cerrillo et al. 2019, doi:10.1016/j.foreco.2018.11.006; Vilà-Vilardell et al. 2024, doi:10.1002/eap.3030;
  Rubio-Cuadrado et al. 2018, doi:10.1016/j.dendro.2018.08.001; Lang et al. 2023, doi:10.1038/s41559-023-02206-6;
  Hunt & Rock 1989, doi:10.1016/0034-4257(89)90046-1; Xiao et al. 2004, doi:10.1016/j.rse.2004.03.010 (all verified
  with scite on 2026-11-28).
- Cite MonitorEO (doi:10.5281/zenodo.23814894), Google Earth Engine (Gorelick et al. 2017,
  doi:10.1016/j.rse.2017.06.031) and the references and credits that each result returns
  (`resultados/casos/C11/referencias_monitoreo.json`).

## Files
- `<everest>/resultados/casos/C11/`: `informe.md`, `estado.json`, `llamadas.json`, `llamadas/` (and `llamadas/errores/`
  with a note), `monitoreo/`, `zonas/`, `scripts/`, `fuentes/ORIGEN.txt` and `fuentes/efda/`, `resumen_baci.csv`,
  `naturalizacion*.json`, `spei12_anual.json`, `figura_naturalizacion.png`. Not published in the results viewer.
