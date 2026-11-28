---
name: everest-c13-microrrefugios-nivales
description: Snow and thermal microrefugia for summit flora and mountain butterflies in the summit zones of four Spanish national parks (Sierra Nevada, Guadarrama, Ordesa y Monte Perdido, Aiguestortes). Landsat snow melt-out day (SMOD) and summer land surface temperature (LST) trends 1985-2025 per pixel, Sentinel-2 SMOD and NDVI 2017-2025, MODIS and ECOSTRESS night LST, terrain (aspect, TWI), a per-pixel refuge index (late, stable snow and less warming) computed outside MonitorEO, and a cross with GBIF records. Use it to repeat this case or to map climate microrefugia in any high-mountain area.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  park: Sierra Nevada, Sierra de Guadarrama, Ordesa y Monte Perdido, Aigüestortes i Estany de Sant Maurici
  wdpa_id: "389011, 555546231, 893, 196014"
  event: "C13 (EVEREST case study)"
  event_date: "1985-2025"
  disturbance: other
  status: validated
  monitoreo_version: "0.3.96"
---

# Snow and thermal microrefugia in the summit zones of four mountain national parks, 1985-2025

> **Versions of MonitorEO.** Computed with MonitorEO 0.3.96, before 0.3.99. Since 0.3.99 a variable of MODIS of the
> catalog is reduced, at its resolution, on the sinusoidal grid of its products (not on pixels of 250-1000 m of the
> UTM zone; data given by collection and band are not); the LST of MODIS has a snow filter on by default (`quality:
> {"snow": false}` for the LST as it was): a repetition gives slightly different MODIS values. The overpass of MODIS
> Terra drifts earlier since 2022 (in 2025 about 9.8 h by day and 20.8-20.9 h by night, local solar time, instead of
> about 11 h and 22 h): trends of its LST that include 2022 or later lean cooler by day and warmer at night; compare
> them with those up to 2021, and check the bands Day_view_time and Night_view_time.

> **Files of this recipe.** `<everest>` is the folder of the EVEREST project where this case was computed. Its local
> scripts (`<everest>/resultados/casos/C13/scripts/`: `gen_llamadas.py` writes the calls, `gbif.py` fetches the
> species records, `refugio.py` computes the refuge index from the GeoTIFFs) and the GBIF file are not part of
> MonitorEO. The MonitorEO calls below are complete; the refuge index (improvement M11) is not yet a MonitorEO tool.
> «status: validated» here means the analysis is complete and every number comes from a file; the refugia are NOT
> validated in the field.

## Question
Which high-mountain spots keep their snow late and have warmed less since 1985, and do they coincide with the summit
flora and the mountain butterflies that persist? It informs where to focus monitoring (soil temperature loggers, flora
plots, butterfly transects), where to limit trampling, intensive grazing and new tracks, and where to collect seed for
ex situ conservation.

## Region and periods
- Summit zones: `{"wdpa_id": W}` with `"where": [{"variable": "ELEVATION", "sensor": "Copernicus", "min": Z}]`:
  Sierra Nevada 389011 / 2800 m, Guadarrama 555546231 / 2000 m, Ordesa 893 / 2500 m, Aigüestortes 196014 / 2500 m
  (cryoromediterranean or alpine belt; thresholds chosen by the analyst).
- No control: the index is relative within each zone (percentiles and medians of the zone).
- Periods: Landsat 1985-2025 (SMOD season 1 January-31 August, the default; LST July-August); Sentinel-2 2017-2025;
  MODIS night LST 2000-2025; ECOSTRESS night LST July-August 2018-2025.
- Sensors: Landsat for the 40-year trends (no harmonize: it does not apply to snow, and LST is not harmonized, so the
  Landsat 5 → 8/9 jump inflates LST trends: use them only to compare pixels); Sentinel-2 for the current snow and
  greenness; MODIS (1 km, one sensor, drifting overpass since 2022) for the regional night warming; ECOSTRESS (70 m) for cold night spots. MODIS
  500 m does not resolve snow patches.

## Steps
All calls with `region` R = `{"wdpa_id": W}` and `where` WH = `[{"variable": "ELEVATION", "sensor": "Copernicus",
"min": Z}]` (one set per park; 13 calls per park, 54 in all with the Sierra Nevada split).

1. Check the images:
   `{"tool": "image_count", "args": {"region": R, "where": WH, "variable": "NDSI", "sensor": "Landsat", "start": "1985-01-01", "end": "2025-12-31", "step": "annual", "season": ["01-01", "08-31"]}}`
   `{"tool": "image_count", "args": {"region": R, "where": WH, "variable": "LST_NIGHT", "sensor": "ECOSTRESS", "start": "2018-07-01", "end": "2025-12-31", "step": "annual", "season": ["07-01", "08-31"]}}`
   (NDSI masks snow, so its per-pixel observations understate those of SMOD: read it only as scenes per year. `SCF`
   cannot be counted with image_count in 0.3.96: it fails asking for metric «mean».)
2. Zone trends (Hamed-Rao):
   `{"tool": "trend_table", "args": {"region": R, "where": WH, "variable": "SMOD", "sensor": "Landsat", "metric": "melt", "start": "1985-01-01", "end": "2025-12-31", "step": "annual", "test": "hamed-rao"}}`
   the same with `"variable": "SCD", "metric": "days"`;
   `{"tool": "trend_table", "args": {"region": R, "where": WH, "variable": "LST", "sensor": "Landsat", "start": "1985-01-01", "end": "2025-12-31", "step": "annual", "season": ["07-01", "08-31"], "metric": "median", "test": "hamed-rao"}}`;
   `{"tool": "trend_table", "args": {"region": R, "where": WH, "variable": "LST_NIGHT", "sensor": "Modis", "start": "2000-01-01", "end": "2025-12-31", "step": "annual", "season": ["07-01", "08-31"], "metric": "median", "test": "hamed-rao"}}`.
3. Per-pixel trends (Mann-Kendall, 30 m):
   `{"tool": "download_trend", "args": {"region": R, "where": WH, "variable": "SMOD", "sensor": "Landsat", "metric": "melt", "start": "1985-01-01", "end": "2025-12-31", "step": "annual", "resolution": 30}}`
   `{"tool": "download_trend", "args": {"region": R, "where": WH, "variable": "LST", "sensor": "Landsat", "start": "1985-01-01", "end": "2025-12-31", "step": "annual", "season": ["07-01", "08-31"], "metric": "median", "resolution": 30}}`
   In Sierra Nevada the SMOD one failed with «User memory limit exceeded»; it was split into
   `"region": {"bbox": [-3.65, 36.9, -3.25, 37.25]}` and `{"bbox": [-3.25, 36.9, -2.55, 37.25]}` with the same WH (the
   summits above 2800 m are inside the park) and mosaicked on the LST trend grid.
4. Current maps (30 m unless noted):
   `{"tool": "download_image", "args": {"region": R, "where": WH, "variable": "SMOD", "sensor": "Sentinel-2", "metric": "melt", "start": "2017-01-01", "end": "2025-12-31", "resolution": 30}}`
   `{"tool": "download_image", "args": {"region": R, "where": WH, "variable": "NDVI", "sensor": "Sentinel-2", "metric": "median", "start": "2017-01-01", "end": "2025-12-31", "season": ["07-01", "08-31"], "temporal": "annual", "interannual": "mean", "resolution": 30}}`
   `{"tool": "download_image", "args": {"region": R, "where": WH, "variable": "LST_NIGHT", "sensor": "ECOSTRESS", "metric": "median", "start": "2018-07-01", "end": "2025-12-31", "season": ["07-01", "08-31"], "resolution": 70}}`
   `{"tool": "download_image", "args": {"region": R, "where": WH, "variable": "ELEVATION", "sensor": "Copernicus", "resolution": 30}}`
   `{"tool": "download_image", "args": {"region": R, "where": WH, "variable": "TWI", "sensor": "MERIT Hydro"}}`
5. Refuge index (outside MonitorEO, `refugio.py`, all layers resampled to the SMOD trend grid): pixels with ≥ 10 years
   in both trends; criteria (a) Sentinel-2 SMOD ≥ 75th percentile of the zone, (b) no significant earlier melt-out
   (not slope < 0 and p < 0.05), (c) LST slope ≤ zone median. Strict refuge = a and b and c; vegetated refuge = strict
   and July-August NDVI ≥ 0.1. Continuous index 0-1 = mean percentile rank of current SMOD, SMOD slope, −LST slope and
   −ECOSTRESS night LST. Summaries by aspect (from the DEM: N, E, S, W) and by TWI terciles.
6. Species: GBIF occurrence search (records with coordinate uncertainty ≤ 100 m) of *Parnassius apollo*, *Agriades
   zullichi*, *Plantago nivalis*, *Androsace ciliata*, *Erebia lefebvrei*; index at their cells vs the zone
   (Mann-Whitney) and share of cells in refugia vs the zone share (binomial).

## Results to expect
From `<everest>/resultados/casos/C13/llamadas/<park>_tt_*.json` (Sen slope per year, p Hamed-Rao):
- SMOD Landsat: Sierra Nevada −0.61 d (p 0.011), Guadarrama −0.78 (0.045), Ordesa −0.41 (0.034), Aigüestortes −0.63
  (< 0.001).
- MODIS night LST July-August 2000-2025: +0.109, +0.131, +0.120, +0.110 °C (all p < 0.001). Inflated by the drift of
  the Terra overpass (MOD11A1 `Night_view_time` from ~22.0 h local solar time in 2000-2021 to ~20.9 h in 2025): over
  2000-2021, +0.065 Sierra Nevada, +0.083 Ordesa, +0.074 Aigüestortes (> 2500 m, simple Kendall; review of 2026-11-28,
  `resultados/casos/C13/revision/`).
- Landsat LST July-August: +0.197 (n 38), +0.095, +0.094, +0.128 °C (inflated by the sensor change).
- SCD Landsat: −0.84 (0.005), −1.48 (0.004), −0.12 (0.79), −0.71 (0.12) days.
From `analisis/resumen.json`: strict refuge 430.5 ha (9.3 %) Sierra Nevada, 275.1 ha (4.8 %) Guadarrama, 152.5 ha
(10.5 %) Ordesa, 289.9 ha (5.8 %) Aigüestortes; vegetated refuge 23.4, 274.2, 38.8 and 141.3 ha. Spearman SMOD-NDVI
−0.50, −0.17, −0.43, −0.55. Ordesa loses 10 797 pixels to the 10-year rule. *Plantago nivalis*: 3 of 28 cells in
vegetated refugia vs 0.5 % of the zone. From `analisis/refugio_por_orientacion.csv`: refugia concentrate on N and E
slopes; E slopes have the lowest LST slope in all four parks.

## Pitfalls
- Per-pixel SMOD trends of large zones exceed Earth Engine memory: split the region (bbox) before retrying.
- Landsat LST trends across the Landsat 5 → 8/9 change are too steep to be warming; use Landsat only to rank pixels.
  MODIS night LST is one sensor but not one hour: the Terra overpass drifts earlier from 2022 (about 1.1 h by 2025),
  which warms the recent nights; end the trend in 2021 or check `Night_view_time`. Before MonitorEO 0.3.99, MODIS LST
  was sampled at 1 km on a UTM grid (small summit zones mix neighbouring pixels) and had no snow filter.
- Most late-snow pixels are rock, scree or near-permanent snow with NDVI < 0.1 (the melt-out-biomass trade-off): add a
  vegetation criterion before calling them refugia for plants.
- Snow that does not melt by 31 August (snow patches, Monte Perdido glacier) has no SMOD and drops out.
- ECOSTRESS night images over these parks are few (11-92 in July-August 2018-2025; 5 of 8 summers empty outside
  Sierra Nevada).
- GBIF records in summits rarely have coordinate uncertainty ≤ 100 m; they are biased to trails.

## Sources and citations
Method and context (DOIs verified with scite): Dedieu et al. 2016 https://doi.org/10.3390/rs8060481; Barrou Dumont et
al. 2025 https://doi.org/10.5194/tc-19-2407-2025; Pauli et al. 2012 https://doi.org/10.1126/science.1219033; Matteodo
et al. 2016 https://doi.org/10.1002/ece3.2354; Scherrer & Körner 2011 https://doi.org/10.1111/j.1365-2699.2010.02407.x;
Dobrowski 2011 https://doi.org/10.1111/j.1365-2486.2010.02263.x; Wilson et al. 2005
https://doi.org/10.1111/j.1461-0248.2005.00824.x and 2007 https://doi.org/10.1111/j.1365-2486.2007.01418.x; Hamed &
Rao 1998 https://doi.org/10.1016/S0022-1694(97)00125-X; Sen 1968 https://doi.org/10.1080/01621459.1968.10480934.
Species: GBIF.org occurrence search (2026-11-28; repeat as a GBIF download to get a DOI). Cite MonitorEO
(https://doi.org/10.5281/zenodo.23814894), Google Earth Engine (https://doi.org/10.1016/j.rse.2017.06.031) and the
references and credits that each result returns (listed in the report).

## Files
`<everest>/resultados/casos/C13/`: `informe.md`, `estado.json`, `llamadas.json`,
`llamadas/`, `monitoreo/`, `analisis/` (`<park>_refugio.tif`, `resumen.json`, CSVs, `fig_indice_refugio.png`),
`scripts/`, `fuentes/`. Not published in the viewer.
