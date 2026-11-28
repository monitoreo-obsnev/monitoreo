---
name: everest-c03-pinsapar-sierra-de-las-nieves
description: Canopy decline, drought stress and stable refugia of the Spanish fir (Abies pinsapo) forest of Sierra de las Nieves National Park (Malaga, Spain), 1985-2025. The fir stands are rebuilt from the REDIAM occurrences published in GBIF; long summer NDVI trends of Landsat by stratum of elevation, aspect and lithology against a neighbouring oak (Quercus faginea) control, detrended summer anomalies of NDVI, MSI and TCW, and a per-pixel Sentinel-2 analysis (2017-2025 NDVI and MSI trends, interannual CV of EVI, tree cover and canopy height) that classifies decline and stable refugia and flags candidate stands for thinning, seed collection and assisted planting. Use it to repeat this case or to adapt it to a slow drought decline of a relict conifer without an official stand map. Partial results, the per-pixel products of Landsat failed (memory of Earth Engine) and the per-pixel decline classes of Sentinel-2 (2017-2025, 9 years) are at chance level.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  park: Parque Nacional de la Sierra de las Nieves
  wdpa_id: "555700945"
  event: "C03 (EVEREST case study)"
  event_date: "1985-2025 (pressure without a date; dry summers 1998, 2005, 2017, 2022-2023)"
  disturbance: drought
  status: partial
  monitoreo_version: "0.3.96-0.3.98"
---

# Spanish fir (pinsapo) decline and refugia, Sierra de las Nieves, 1985-2025

> **Files of this recipe.** `<everest>` is the folder of the EVEREST project where this case was computed:
> its zones (`resultados/casos/C03/zonas/*.gpkg`), its local scripts
> (`resultados/casos/C03/scripts/`) and its state files are not part of MonitorEO. To repeat the case, rebuild the
> zones with those scripts (or with a stand map, if one becomes available) and run the calls below. See
> `monitoreo-disturbance-case-study` for the general method.

## Question
In which bands of elevation, aspect and substrate are the loss of greenness and the water stress of the pinsapo forest
concentrated since 1985, and which stands stay stable (refugia)? It informs where to thin dense low stands, where to
reinforce regeneration or collect seed, which stands to protect as refugia and where to plant (assisted migration).

## Region and periods
- Fir stands: no official stand map could be used (REDIAM download server: certificate not verified; MITECO MFE25:
  captcha). `scripts/descargar_gbif.py` downloads the GBIF occurrences of *Abies pinsapo* in lat 36.55-36.78, lon
  -5.15/-4.85; `scripts/zonas_pinsapar.py` keeps those of the REDIAM dataset (datasetKey
  fa7e6ad8-0a2e-49f2-b95d-e9f1e380fadf, DOI 10.15470/zatyqi) inside the park (OSM boundary), buffers them 50 m, merges
  them and keeps patches >= 3 ha: `{"file": "<everest>/resultados/casos/C03/zonas/pinsapar.gpkg", "name_field":
  "region"}`, 1,245.1 ha (`zonas/zonas_resumen.json`).
- Control: the same with *Quercus faginea* (minus 60 m around the fir): `quejigar_control`, 198.9 ha, in
  `zonas/pinsapar_y_quejigar.gpkg`. A deciduous oak is not a perfect control (it responds to drought too); it serves
  to see the shared sensor and climate signal.
- Strata (`scripts/estratos.py`, from the ELEVATION and ASPECT GeoTIFFs of step 2): bands <1000, 1000-1200, 1200-1400,
  >=1400 m x north (315-45 deg), south (135-225 deg), east/west, on carbonate/detrital rocks; fir on peridotites
  (IGME 1:200,000 + 1:1,000,000, only 39.3 ha) as one stratum; plus the control: `zonas/estratos.gpkg` (14 features).
- Periods: summer 15 Jun - 15 Sep (the fir is evergreen; avoids winter shadow and snow). Landsat 1985-2025 (no data in
  2012); Sentinel-2 2017-2025 (EVI CV from 2018, first full year).
- Sensors: Landsat with `quality {"harmonize": true}` for the long series (only by region: per-pixel Landsat failed);
  Sentinel-2 at 10 m for the per-pixel analysis; TerraClimate and ERA5-Land for the climate of the park.

## Steps
All calls are in `<everest>/resultados/casos/C03/llamadas.json`, run with `herramientas/mcp_calls.py casos/C03 ...`.
P = pinsapar.gpkg, E = estratos.gpkg, PQ = pinsapar_y_quejigar.gpkg (all with `"name_field": "region"`).

1. Images per summer:
   `image_count {"region": P, "variable": "NDVI", "sensor": "Sentinel-2", "start": "2017-01-01", "end": "2025-12-31", "step": "annual", "season": ["06-15","09-15"]}`;
   the same with `"sensor": "Landsat", "quality": {"harmonize": true}, "scale": 90` for 1985-2004 and 2005-2025 (a
   single 1985-2025 call ran for 20 min without answer: split it).
2. Fixed layers (GeoTIFF, `"crs": "EPSG:25830", "resolution": 30`, region P): `download_image` of ELEVATION and
   ASPECT and SLOPE (Copernicus), TWI (MERIT Hydro), TREE_COVER (Hansen), CANOPY_HEIGHT (ETH). Then run
   `scripts/estratos.py` to build E.
3. Long NDVI trend by stratum:
   `trend_table {"region": E, "variable": "NDVI", "sensor": "Landsat", "start": "1985-01-01", "end": "2025-12-31", "season": ["06-15","09-15"], "step": "annual", "metric": "median", "test": "hamed-rao", "scale": 30, "quality": {"harmonize": true}}`
   (48 min with a busy shared quota).
4. Summer anomalies of the fir and the control:
   `anomalies {"region": PQ, "variable": "NDVI" | "MSI" | "TCW", "sensor": "Landsat", "start": "1985-01-01", "end": "2025-12-31", "season": ["06-15","09-15"], "step": "annual", "metric": "median", "threshold": 1.5, "quality": {"harmonize": true}}`;
   its z is against all summers and so dominated by the trend: `scripts/anomalias_sin_tendencia.py <case> ndvi|msi|tcw`
   removes the Sen line of each series by sensor era (1985-2011, 2013-2025) and standardizes the residuals.
5. Per-pixel Sentinel-2 (region P, `"crs": "EPSG:25830", "resolution": 10`):
   `download_trend {"variable": "NDVI" | "MSI", "sensor": "Sentinel-2", "start": "2017-01-01", "end": "2025-12-31", "season": ["06-15","09-15"], "step": "annual", "metric": "median", "test": "mk"}`;
   `download_image {"variable": "EVI", "sensor": "Sentinel-2", "start": "2018-01-01", "end": "2025-12-31", "temporal": "annual", "metric": "mean", "interannual": "cv"}`
   (stability), and with `"metric": "cv", "interannual": "cv"` (stability of seasonality) and `"metric": "mean",
   "interannual": "mean"`; `trend_map` of the NDVI with `"alpha": 0.05` for the figure.
6. `region_stats {"region": E, "variable": "EVI", "sensor": "Sentinel-2", "start": "2018-01-01", "end": "2025-12-31", "temporal": "annual", "metric": "cv", "interannual": "cv", "stats": ["mean","median","p10","p90"], "scale": 10}`.
7. Drought map: `compare_map {"region": P, "variable": "NDVI", "sensor": "Sentinel-2", "start": "2018-01-01", "end": "2021-12-31", "other_start": "2023-01-01", "other_end": "2023-12-31", "season": ["06-15","09-15"], "metric": "median", "z": true}`.
8. Climate of the park (`{"wdpa_id": 555700945}`, `"test": "hamed-rao"`): `trend_table` of CWD and PRECIP
   (TerraClimate, 1985-2024, annual, metric sum) and TMAX (ERA5-Land, 1985-2025, season 06-01 to 08-31, metric mean).
9. Local: `scripts/analisis_pixeles.py <case>` (classes and candidates, `analisis/resumen_*.csv`,
   `analisis/clases_pinsapar.tif`, `analisis/candidatos_gestion.tif`) and `scripts/figuras.py <case>`.
   Classes: decline or stress = Sentinel-2 NDVI trend negative and p < 0.05, or MSI trend positive and p < 0.05;
   stable refugium = neither, NDVI slope >= 0 and interannual CV of EVI <= the median of the fir (4.62 %); the rest
   intermediate. Candidates: thinning = decline and < 1200 m and tree cover >= 70 %; seed and refugium = refugium and
   cover >= 70 % and canopy >= 10 m; assisted planting = refugium and cover < 50 % and >= 1200 m.

«now»: with a stand map (REDIAM pinsapares, MFE25) use it as the region `{"file": ...}` instead of the GBIF buffers;
`control_ring` with `match ["ELEVATION"]` would give an elevation-matched ring, but around the fir it would be mostly
other forest and scrub, so the oak polygon was preferred.

## Results to expect
- Fir 1,245.1 ha; control 198.9 ha; fir on peridotites 39.3 ha (`zonas/zonas_resumen.json`). Elevation 640-1762 m
  (`llamadas/img_elevation.json`).
- Landsat summer valid observations per pixel 3.0-19.8, none in 2012 (`llamadas/n_img_ndvi_landsat_*.json`);
  Sentinel-2 21-50 (`llamadas/n_img_ndvi_s2.json`).
- NDVI 1985-2025 Sen slopes, all p <= 0.0005: control 0.00398/yr; fir strata 0.00230 (>=1400 m south) to 0.00508
  (peridotites); >=1400 m 0.0023-0.0032, below 1200 m 0.0042-0.0047 (`llamadas/tt_ndvi_L_estratos.json`).
- Within sensor eras (`analisis/anomalias_sin_tendencia_ndvi.csv`): fir +0.0026/yr in 1985-2011 (control +0.0031) and
  +0.0022/yr in 2013-2025 (control +0.0013). Detrended summer z of the fir NDVI: 1998 -2.08, 2017 -1.48, 2023 -1.28,
  1988 -1.21, 2004 -1.18, 2005 -1.05. MSI within eras (`analisis/anomalias_sin_tendencia_msi.csv`): fir -0.0025/yr
  (1985-2011) and -0.0047/yr (2013-2025), control -0.0028 and -0.0030; detrended MSI z of the fir highest in 2023
  (+2.76; control +1.77), then 1999 (+2.03) and 2005 (+1.37). TCW within eras (`analisis/anomalias_sin_tendencia_tcw.csv`): fir
  +0.00048/yr and +0.00103/yr, control +0.00044 and +0.00056; driest detrended TCW of the fir 2015 (-2.29), 1985
  (-2.23), 1999 (-1.96), 1997 (-1.40), 2023 (-1.33). Anomalies calls: 39-42 min each.
- Sentinel-2 2017-2025 (`analisis/resumen_pixeles.json`): 124,443 pixels (1,244.4 ha); decline or stress 57.7 ha,
  intermediate 825.5 ha, stable refugium 361.3 ha; NDVI significant decrease 3.7 %, increase 10.1 %; MSI increase
  1.6 %, decrease 16.6 %. Decline highest on north slopes 1000-1200 m (10.3 %) and 1200-1400 m (8.3 %), lowest >=1400 m
  (1.4-2.8 %); by tree cover 2.1 % (<50 %) to 9.6 % (>=85 %); by canopy height 1.6 % (<5 m) to 7.3 % (>=15 m).
  Candidates: thinning 16.9 ha, seed and refugium 94.2 ha, assisted planting 181.1 ha. Read these classes as a
  relative ranking: with 9 summers and per-pixel p < 0.05, about 2.3 % of pixels fall in each "significant" direction
  by chance, so the 4.6 % of decline or stress overall is at chance level (only north slopes 1000-1400 m and cover
  >= 85 % stand out), and about 25 % of pixels are "refugium" by the definition itself.
- Climate (`llamadas/tt_*_parque.json`, `tt_tmax_ERA5_verano.json`): CWD +2.73 mm/yr (p 0.020), precipitation
  -1.36 mm/yr (p 0.44), summer TMAX +0.064 degC/yr (p 0.0001).

## Pitfalls
- **Per-pixel Landsat products failed** with «User memory limit exceeded» (download_trend, trend_map, download_image
  with interannual cv, compare_map with z, region_stats with temporal annual over 14 features) for 1985-2025, 1985-2011
  and 2013-2025, with or without `harmonize`, MK or Hamed-Rao, mean or median, whole region or halves, while seven
  other EVEREST cases shared the quota (`llamadas/fallidas/llamadas_fallidas.json`). Region-level Landsat calls worked
  but slowly (trend_table of 14 strata x 41 years: 48 min; anomalies of 2 regions: 39 min). Sentinel-2 per pixel worked.
- Per-pixel Mann-Kendall with n = 9 and no multiple-test correction: compare class shares with the chance level
  (~2.3 % per direction) before calling a decline; a longer series (Landsat per pixel, when the quota allows) is needed.
- The z of `anomalies` against all the summers of a greening series is mostly the trend: detrend by sensor era.
- The Landsat 5/7 -> 8/9 jump inflates long trends: compare with the control and within eras.
- GBIF occurrences: REDIAM points are dense (median spacing 45 m) but not a stand map; herbarium and iNaturalist points
  were dropped (fewer, with variable coordinate uncertainty; some may be cultivated trees).
- The IGME GEODE 50 REST service does not allow queries; the 1:200,000 sheet does not cover the north of the park.

## Sources and citations
Linares et al. (2009) https://doi.org/10.1111/j.1466-8238.2009.00465.x; Linares et al. (2010)
https://doi.org/10.1111/j.1365-2745.2010.01645.x; Lechuga et al. (2019) https://doi.org/10.3390/f10121132; Ariza
Salamanca et al. (2024) https://doi.org/10.3390/rs16173182; Cabello et al. (2012)
https://doi.org/10.1007/s10531-012-0370-7; Hunt & Rock (1989) https://doi.org/10.1016/0034-4257(89)90046-1; Crist
(1985) https://doi.org/10.1016/0034-4257(85)90102-6; Hamed & Rao (1998) https://doi.org/10.1016/S0022-1694(97)00125-X;
Sen (1968) https://doi.org/10.1080/01621459.1968.10480934 (all verified with scite on 2026-11-28). REDIAM occurrences
in GBIF https://doi.org/10.15470/zatyqi. Cite MonitorEO (https://doi.org/10.5281/zenodo.23814894), Google Earth Engine
(https://doi.org/10.1016/j.rse.2017.06.031) and the references and credits that each result returns (listed in the
report).

## Files
`<everest>/resultados/casos/C03/`: `informe.md`, `estado.json`, `llamadas.json`,
`llamadas/` (responses and PNG; `fallidas/`), `monitoreo/` (CSV, PNG, GeoTIFF, README), `zonas/`, `analisis/`,
`scripts/`, `fuentes/` (`ORIGEN.txt`). Not published in the viewer.
