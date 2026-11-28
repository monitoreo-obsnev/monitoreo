---
name: everest-c01-borreguiles-sierra-nevada
description: Snow melt-out, late-summer greenness and moisture of the borreguiles (high-mountain wet meadows) of Sierra Nevada National Park (Spain). Snow melt-out day (SMOD) of Landsat 1985-2025 and Sentinel-2 2018-2025 per meadow, late-summer (15 July-15 September) NDVI, WAVI and LSWI of Sentinel-2 and harmonized Landsat, Sentinel-2 16-day NDVI for the green season, Hamed-Rao trends, an elevation-matched control of dry summit grassland, and the per-meadow sensitivity of greenness to melt-out (slope NDVI ~ SMOD, as Albano et al. 2019) related to elevation and TWI. Use it to repeat this case or to adapt it to snow-fed meadows, fens or wet pastures in any mountain range.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  park: Sierra Nevada National Park
  wdpa_id: "389011"
  event: "C01 (EVEREST case study)"
  event_date: "1985-2025"
  disturbance: other
  status: validated
  monitoreo_version: "0.3.96"
---

# Snow melt-out and late-summer greenness of the borreguiles of Sierra Nevada, 1985-2025

> **Files of this recipe.** `<everest>` is the folder of the EVEREST
> project where this case was computed. The meadow polygons (`<everest>/resultados/casos/C01/zonas/*.gpkg`, made from
> an open PANGAEA map, see below), the local analysis script (`<everest>/resultados/casos/C01/scripts/analisis_c01.py`)
> and the call runner (`<everest>/herramientas/mcp_calls.py`) are not part of MonitorEO. To repeat the case elsewhere,
> make a GeoPackage with one polygon per meadow and an `id` field, and a second one with the dry grassland around them;
> the rest are MonitorEO calls. See `monitoreo-disturbance-case-study` for the control and trend method.

## Question
Has snow melt-out come earlier over the borreguiles (snow-fed wet meadows, habitats 7140 and 6230*) of Sierra Nevada,
and do their late-summer greenness, moisture and green-season length respond to it? Which meadows are most sensitive?
It informs where to prioritize the traditional recharge channels (acequias de careo) and hydrological restoration,
how to set the yearly grazing entry date and stocking rate, and which meadows to include in habitat monitoring.

## Region and periods
- Meadows: class 2 «Borreguiles» (64 polygons, 1,029.8 ha, 5-82 ha each) of Pérez-Luque, Bonet-García & Zamora
  Rodríguez (2019), Map of Ecosystems Types in Sierra Nevada mountain, PANGAEA, https://doi.org/10.1594/PANGAEA.910176
  (CC BY 4.0; zip 14.7 MB; CRS UTM 30N on the Hayford ellipsoid, read as EPSG:23030). Numbered west to east B01-B64 and
  written to `zonas/borreguiles.gpkg` (fields `id`, `ha`, `lon`, `lat`) and their union to
  `zonas/borreguiles_union.gpkg` (field `region`). The official REDIAM/OBSNEV wetland map was not usable (its download
  server's certificate could not be verified).
- Control: class 13 «Pastizales, canchales y roquedos de Alta Montaña» of the same map within 3 km of the meadows
  (`zonas/pastos_cumbre.gpkg`), used as `within` of `control_ring` (gap 100 m, width 3,000 m, matched by elevation):
  15,049.6 ha of control vs 1,030.2 ha of meadows, `where` ELEVATION 1,939.95-2,851.81 m. A 500 m ring (6,553.8 ha)
  was made for the Landsat control series (see Pitfalls).
- Periods and seasons: SMOD season 1 March-31 August (the season of the SMOD validation in borreguiles), Sentinel-2
  2018-2025 (2017 dropped: Sentinel-2 SR starts 2017-03-28), Landsat 1985-2025; late-summer window 15 July-15
  September (median); green season April-November, 16-day steps.
- Sensors: Sentinel-2 (10-20 m) and Landsat (30 m; `harmonize` for NDVI and LSWI; SMOD needs none). MODIS is too
  coarse for meadows of a few hectares. Climate (ERA5-Land, TerraClimate) only as context over the park.

## Steps
`B` = `{"file": "<everest>/resultados/casos/C01/zonas/borreguiles.gpkg", "name_field": "id"}`;
`U` = `{"file": "<everest>/resultados/casos/C01/zonas/borreguiles_union.gpkg", "name_field": "region"}`;
`AC` = `{"file": "<control_ring file>", "name_field": "region"}` with `"where": [{"variable": "ELEVATION", "sensor":
"Copernicus", "min": 1939.952401675184, "max": 2851.810402349577}]`. All calls in
`<everest>/resultados/casos/C01/llamadas.json` (ids in brackets).

1. Check the images [`ic_s2`, `ic_landsat`]:
   ```json
   {"tool": "image_count", "args": {"region": U, "variable": "NDVI", "sensor": "Sentinel-2",
    "start": "2017-03-28", "end": "2025-12-31", "step": "annual", "season": ["03-01", "09-30"]}}
   ```
   and the same with `"sensor": "Landsat", "start": "1985-01-01"` (took 10 min).
2. Control [`control`]:
   ```json
   {"tool": "control_ring", "args": {"region": U, "gap": 100, "width": 3000,
    "within": {"file": "<everest>/resultados/casos/C01/zonas/pastos_cumbre.gpkg", "name_field": "region"},
    "match": ["ELEVATION"]}}
   ```
   (now) `ring: true` in `time_series` gives a ring without the `within`; here the `within` keeps the control on dry
   summit grassland and rock instead of forest or other meadows.
3. Terrain per meadow [`elev`, `twi`]: `region_stats` with `"region": B`, `"variable": "ELEVATION", "sensor":
   "Copernicus", "stats": ["mean", "min", "max"]` and `"variable": "TWI", "sensor": "MERIT Hydro", "stats": ["mean",
   "median", "max"]`.
4. Snow melt-out per meadow and for meadows vs control [`smod_s2_b`, `smod_s2_ac`, `smod_l_ts_b`]:
   ```json
   {"tool": "time_series", "args": {"region": B, "variable": "SMOD", "sensor": "Sentinel-2",
    "start": "2018-01-01", "end": "2025-08-31", "step": "annual", "metric": "melt", "season": ["03-01", "08-31"]}}
   ```
   the same with `"region": AC` plus the `where`, and with `"sensor": "Landsat", "start": "1985-01-01"` (13 min).
   Landsat SMOD of meadows vs control [`control_500`, `smod_l_ac500`]: the 3 km control exceeded Earth Engine memory
   (`smod_l_ac`, `smod_l_ac_90`, `smod_l_ts_ac_8598` failed), so make a 500 m ring (`control_ring` as in step 2 with
   `"width": 500`) and run `trend_table` SMOD Landsat on it with `"scale": 60` and the same `where` (57 min).
5. Trends per meadow [`smod_l_b`, `ndvi_l_b`, `lswi_l_b`]:
   ```json
   {"tool": "trend_table", "args": {"region": B, "variable": "SMOD", "sensor": "Landsat", "start": "1985-01-01",
    "end": "2025-08-31", "step": "annual", "metric": "melt", "season": ["03-01", "08-31"], "test": "hamed-rao"}}
   ```
   and for `NDVI` and `LSWI` with `"end": "2025-12-31", "metric": "median", "season": ["07-15", "09-15"],
   "quality": {"harmonize": true}` (11-17 min each). trend_table writes only the trends, not the yearly values: for
   them use `time_series` (step 4, step 6). Meadows vs control [`ndvi_l_ac`, `lswi_l_ac`]: the same with `"region":
   AC` plus the `where` (one hour each with the 3 km ring).
6. Late-summer greenness and moisture [`ndvi_s2_b`, `wavi_s2_b`, `lswi_s2_b`, the same `_ac`, `ndvi_l_ts_b`]:
   ```json
   {"tool": "time_series", "args": {"region": B, "variable": "NDVI", "sensor": "Sentinel-2",
    "start": "2017-03-28", "end": "2025-12-31", "step": "annual", "metric": "median", "season": ["07-15", "09-15"]}}
   ```
   with `WAVI` and `LSWI` (MSI, also in MonitorEO, was not used: LSWI carries the same NIR/SWIR information), with `"region": AC`
   plus the `where`, and Landsat NDVI with `"start": "1985-01-01", "quality": {"harmonize": true}`.
7. Green season [`ndvi16_b`]: `time_series` NDVI Sentinel-2, `"region": B`, `"step": "16-day", "metric": "median",
   "season": ["04-01", "11-30"]`, 2017-03-28 to 2025-11-30. Start, peak, end (first/last step above half the yearly
   amplitude), length and integral are computed locally (`scripts/analisis_c01.py`) until MonitorEO has phenology
   metrics (M01).
8. Climate context [`tmean_spring`, `tmax_summer`, `precip_annual`, `cwd_annual`]: `trend_table` over
   `{"wdpa_id": 389011}`, `"test": "hamed-rao"`: `TMEAN` ERA5-Land `"metric": "mean", "season": ["03-01", "06-30"]`, `TMAX` ERA5-Land
   `"metric": "mean", "season": ["06-01", "08-31"]`, `PRECIP` ERA5-Land and `CWD` TerraClimate with `"metric": "sum"`, `"start": "1985-01-01"` and
   `"end"` 2025-06-30 (TMEAN), 2025-08-31 (TMAX), 2025-09-30 (PRECIP), 2024-12-31 (CWD). SPEI (`SPEIbase`, 0.5°) is in the catalog but was not used.
9. Sensitivity (local, `scripts/analisis_c01.py`): per meadow, OLS slope of late-summer NDVI on SMOD across years
   (Landsat, dropping years with a median of fewer than 5 Landsat images in the season: 1985, 2006, 2011, 2012;
   Sentinel-2 as a check), in NDVI per 10 days of later melt-out; Spearman correlation with elevation and TWI; priority
   = rank of sensitivity + rank of the SMOD trend.

## Results to expect
- Images: Sentinel-2 106-249 images per season, 31-45 valid observations per pixel, full coverage every year
  (`llamadas/ic_s2.json`); Landsat 2-15 valid observations per pixel and season, none in 2012, 58 % coverage in 2008
  (`llamadas/ic_landsat.json`).
- SMOD Landsat trend per meadow 1985-2025: median −0.34 d/year (mean −0.30), negative in 51 of 64, significant
  negative in 9, significant positive in 0 (`monitoreo/trend_SMOD_Landsat_annual_1985-01-01_2025-08-31_hamed-rao_20261128-154343.csv`);
  ≈ −13.7 days in 40 years. Mean of all meadows: Sen −0.32 d/year, Kendall p = 0.19 (`analisis/resumen.json`).
- SMOD Sentinel-2, mean of the meadows 2018-2025: 129, 106, 107, 83, 118, 71, 110, 111; Landsat vs Sentinel-2 r = 0.76,
  Landsat 8.7 days later on average (n = 512 meadow-years). Meadows lose snow 12.2 days earlier than the control.
- Late-summer meadows − control (Sentinel-2, mean 2017-2025): NDVI +0.233, WAVI +0.162, LSWI +0.069.
- Sensitivity (Landsat): median 0.0055 NDVI per 10 days of later melt-out; positive in 63 of 64 meadows, significant
  (p < 0.05) in 34, never significantly negative; year-to-year r of the meadow means 0.43 (37 years). Spearman with
  elevation ρ = 0.68; ≥ 2,400 m median 0.0093 (23 of 24 significant) vs 0.0042 below; with TWI ρ = −0.03 (p = 0.81)
  (`analisis/resumen.json`, `analisis/borreguiles_sensibilidad.csv`).
- Green season (within-meadow, per day of later melt-out): end +0.82 d, length +0.89 d, peak +0.34 d, integral
  +0.45 NDVI·d (all p < 1e-6, n = 512); start unrelated (r = −0.07). 2023, the earliest melt-out (day 71), had the
  poorest season (integral 27.7) (`analisis/estacion_verde.csv`).
- Landsat meadows vs control: SMOD −0.35 d/year (p = 0.24) vs −0.47 d/year (p = 0.08, 500 m ring; trend CSV
  `monitoreo/trend_SMOD_Landsat_annual_1985-01-01_2025-08-31_hamed-rao_20261128-165435.csv`); late-summer NDVI
  +0.0008/year (p = 0.19) vs −0.0010/year (p = 0.005, 3 km ring;
  `monitoreo/trend_NDVI_Landsat_annual_1985-01-01_2025-12-31_hamed-rao_20261128-163126.csv`); LSWI +0.0004/year (p = 0.21) vs −0.0005/year (p = 0.003)
  (`monitoreo/trend_LSWI_Landsat_annual_1985-01-01_2025-12-31_hamed-rao_20261128-173111.csv`).
- Priority meadows: B33, B32, B08, B35, B31, B45, B10, B51, B16, B49 (2,361-2,784 m).
- Climate over the park: spring TMEAN +0.056 °C/year and summer TMAX +0.065 °C/year (p = 0.0001), annual
  precipitation −0.57 mm/year (p = 0.72), CWD +3.03 mm/year (p = 0.004).
- Long-term late-summer NDVI and LSWI of the meadows did not decrease: median Sen +0.0007 and +0.0005 per year;
  25 and 21 meadows significantly up, 4 and 3 down.

## Pitfalls
- SMOD is censored at the season start: a pixel without snow on 1 March takes the day of its first clear image. 19.7 %
  of the Sentinel-2 values are day 70 or earlier, and 15 meadows (median 2,061 m) have 3 or more such years. Read the
  sensitivity of the low meadows with care, or start the season in January for them.
- The Landsat control series with the 3,000 m ring (15,050 ha) failed with «User memory limit exceeded» in
  `trend_table` (also with `scale` 90) and in a 14-year `time_series`: keep Landsat SMOD regions to a few thousand
  hectares or use a narrower ring (`width` 500).
- `trend_table` gives no yearly values: run `time_series` with the same arguments to regress one variable on another.
- The ecosystem map polygons include dry slope around the wet patches and some low wet meadows (from 1,758 m); the
  REDIAM/OBSNEV detailed map would be better. TWI at 90 m cannot resolve hollows of tens of metres.
- The control melts out 12 days later than the meadows: it is a «neighbouring dry grassland» control, not a matched
  meadow.
- Landsat 5/7 → 8/9 can inflate long NDVI/LSWI trends even with `harmonize`; read the difference with the control.
- Precipitation 2025 is partial (to September).

## Sources and citations
- Meadows: Pérez-Luque, A. J., Bonet-García, F. J., & Zamora Rodríguez, R. (2019). Map of Ecosystems Types in Sierra
  Nevada mountain (southern Spain). PANGAEA. https://doi.org/10.1594/PANGAEA.910176
- Method: Albano et al. (2019), Ecohydrology, https://doi.org/10.1002/eco.2128; Choler (2015), Biogeosciences,
  https://doi.org/10.5194/bg-12-3885-2015; Dedieu et al. (2016), Remote Sensing, https://doi.org/10.3390/rs8060481;
  Barrou Dumont et al. (2025), The Cryosphere, https://doi.org/10.5194/tc-19-2407-2025; Hamed & Rao (1998), Journal of
  Hydrology, https://doi.org/10.1016/S0022-1694(97)00125-X; Sen (1968), https://doi.org/10.1080/01621459.1968.10480934.
  All DOIs verified with scite `verify_papers` (2026-11-28).
- Cite MonitorEO (https://doi.org/10.5281/zenodo.23814894), Google Earth Engine
  (https://doi.org/10.1016/j.rse.2017.06.031) and the references and credits that each result returns (listed in
  `resultados/casos/C01/informe.md`).

## Files
`<everest>/resultados/casos/C01/`: `informe.md` (report, Spanish), `estado.json`,
`llamadas.json` and `llamadas/` (calls and responses), `monitoreo/` (CSV, PNG, README of MonitorEO), `analisis/`
(`resumen.json`, `borreguiles_sensibilidad.csv`, `estacion_verde.csv`, figures), `zonas/` (meadows and control
polygons), `fuentes/` (PANGAEA map and `ORIGEN.txt`), `scripts/analisis_c01.py`. Not published in the viewer.
