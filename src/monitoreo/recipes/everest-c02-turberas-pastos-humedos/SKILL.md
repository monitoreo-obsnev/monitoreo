---
name: everest-c02-turberas-pastos-humedos
description: Are mountain peatlands and wet meadows drying, and which to restore first? Peatlands (habitat 7140) of Peneda-Gerês (ICNF PSRN2000 polygons), Comeya and Fuenfría in Picos de Europa (Spanish Wetland Inventory) and approximate borreguiles of Sierra Nevada (summer NDVI and elevation). Per-peatland Mann-Kendall/Sen trends of summer LSWI, MSI, TCW and NDVI of harmonized Landsat (1985-2025) and LSWI, MSI, NDWI, WAVI and NDVI of Sentinel-2 (2017-2025), late-winter NDVI for woody encroachment, % of area drying per pixel, a peatland-minus-ring BACI by sector, dry years with TerraClimate SOILM and CWD, a dNBR fire check, and a priority index for the EU Nature Restoration Regulation. Use it to repeat this case or to adapt it to any set of small wetlands, mires or wet meadows.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  park: Peneda-Gerês, Sierra Nevada and Picos de Europa National Parks
  wdpa_id: "860, 389011, 71213"
  event: "C02"
  event_date: "1985-2025"
  disturbance: drought
  status: validated
  monitoreo_version: "0.3.96"
---

# Drying of peatlands and wet meadows, Peneda-Gerês, Sierra Nevada and Picos de Europa, 1985-2025

> **Files of this recipe.** `<everest>` is the folder of the EVEREST project where this case was computed,
> and `<C02>` = `<everest>/resultados/casos/C02`. Its zones (`<C02>/*.gpkg`),
> local scripts (`<C02>/scripts/`) and external sources (`<C02>/fuentes/`) are not part of MonitorEO. To repeat the
> case, rebuild the zones from the same official sources (step 1), then run the calls below. See
> `monitoreo-disturbance-case-study` for the general method (control ring, BACI).

## Question
Do peatlands and wet meadows show a drying trend (less surface and vegetation water in summer, more woody greenness in
late winter), and which ones have degraded most? It informs the restoration plans of Regulation (EU) 2024/1991 (block
drains, remove woody plants, regulate trampling) and the follow-up of restoration works.

## Region and periods
- Peneda-Gerês: polygons with habitat 7140 (in mosaic with 4010, 4020, 6230, 7150) of the ICNF PSRN2000 habitat layer,
  WFS `https://si.icnf.pt/wfs/psrn2000_habitats_nacional`, layer `BDG:psrn2000_habitats_nacional`, filter
  `site_code='PTCON0001' AND cod_hab_n3='7140'`, kept if >= 1 ha (72 polygons, 970.6 ha), grouped in sectors CL (Castro
  Laboreiro plateau, lat > 41.98), MO (Mourela/Pitões, lon > -7.96), PS (Peneda-Soajo, lon < -8.2) and GE (Gerês/Amarela)
  (`scripts/zonas_pg_picos.py`). In MonitorEO >= 0.3.94 the WFS can be given directly as `{"wfs": URL, "layer": ...}`.
- Picos de Europa: Turbera de Comeya (IH120049, 26.0 ha) and Fuenfría (IH120019, 0.7 ha) of the Inventario Español de
  Zonas Húmedas 2025 (MITECO shapefile).
- Sierra Nevada: approximate borreguiles (no official layer used): patches >= 1 ha of summer NDVI >= 0.40 (call
  `sn_ndvi_verano_img`), mean elevation >= 2,500 m (call `sn_cand_elev`): 60 patches, 128.6 ha (`scripts/zonas_sn.py`,
  `scripts/filtra_sn.py`). Replace them with official polygons when available.
- All merged in `turberas.gpkg` (134 features, field `id`), dissolved by sector in `sectores.gpkg` (field `sector`), one
  file per sector `sector_<S>.gpkg` (for the ring) and `turberas_<S>.gpkg` (for area_by_class)
  (`scripts/zonas_todas.py`).
- Periods: summer 07-01/09-30, annual median; Landsat 1985-2025 with `{"harmonize": true}`; Sentinel-2 2017-2025;
  late winter 02-01/03-31 (heath green, grass not; snow in Sierra Nevada and Picos); TerraClimate 1985-2024.
- Sensors: Landsat for the 40-year trend, Sentinel-2 (10-20 m) for the small mires and the recent years.

## Steps
All calls are in `<C02>/llamadas.json` and were run with
`python <everest>/herramientas/mcp_calls.py casos/C02 <C02>/llamadas.json`.

1. Approximate borreguiles (only where there is no official layer):
   ```json
   {"tool": "download_image", "args": {"region": {"wdpa_id": 389011}, "variable": "NDVI", "sensor": "Sentinel-2",
    "start": "2017-01-01", "end": "2025-12-31", "season": ["07-15", "09-15"], "metric": "median", "temporal": "annual",
    "interannual": "median", "resolution": 20, "crs": "EPSG:25830",
    "where": [{"variable": "ELEVATION", "sensor": "Copernicus", "min": 2300},
              {"landcover": "WorldCover", "year": 2021, "exclude": ["water", "built", "trees", "cropland"]}]}}
   ```
   Threshold >= 0.40, polygonize, keep >= 1 ha; then `region_stats` of `ELEVATION` (Copernicus) per patch, keep mean >= 2,500 m.
2. Check the images: `image_count` of LSWI, Sentinel-2 2017-2025 and Landsat 1985-2025 (`"quality": {"harmonize": true}`),
   `"step": "annual"`, `"season": ["06-15", "09-30"]`, region `{"file": "<C02>/zonas_pg_picos.gpkg", "name_field": "id"}`.
3. Per-peatland trends (one call per index; region `{"file": "<C02>/turberas.gpkg", "name_field": "id"}`):
   ```json
   {"tool": "trend_table", "args": {"region": {"file": "<C02>/turberas.gpkg", "name_field": "id"}, "variable": "LSWI",
    "sensor": "Landsat", "start": "1985-01-01", "end": "2025-12-31", "step": "annual", "season": ["07-01", "09-30"],
    "metric": "median", "test": "hamed-rao", "quality": {"harmonize": true}}}
   ```
   Same with MSI, TCW, NDVI (Landsat); NDVI with `"season": ["02-01", "03-31"]`; LSWI, MSI, WAVI, NDVI and NDWI
   (`"quality": {"water": false}`) of Sentinel-2 2017-2025 without harmonize; NDVI Sentinel-2 late winter.
4. The same `trend_table` over `{"file": "<C02>/sectores.gpkg", "name_field": "sector"}` for LSWI, TCW, late-winter NDVI
   (Landsat) and LSWI (Sentinel-2), and SOILM and CWD (TerraClimate, `"metric": "mean"`, summer) and PRECIP
   (`"metric": "sum"`, no season), 1985-2024.
5. Share of each peatland drying per pixel (split by sector: all 134 at once gave «User memory limit exceeded»):
   ```json
   {"tool": "area_by_class", "args": {"region": {"file": "<C02>/turberas_CL.gpkg", "name_field": "id"}, "variable": "LSWI",
    "sensor": "Landsat", "trend": true, "start": "1985-01-01", "end": "2025-12-31", "step": "annual",
    "season": ["07-01", "09-30"], "metric": "median", "quality": {"harmonize": true}}}
   ```
6. BACI against the surroundings (one call per sector; the ring excludes the other peatlands):
   ```json
   {"tool": "time_series", "args": {"region": {"file": "<C02>/sector_MO.gpkg"}, "variable": "LSWI", "sensor": "Landsat",
    "start": "1985-01-01", "end": "2025-12-31", "step": "annual", "season": ["07-01", "09-30"], "metric": "median",
    "quality": {"harmonize": true},
    "ring": {"gap": 100, "width": 1000, "exclude": {"file": "<C02>/turberas.gpkg"}}}}
   ```
   Also with late-winter NDVI for CL and MO. The Mann-Kendall/Sen of the `affected - control` series was computed
   locally (`scripts/analisis.py`).
7. Dry years: `anomalies` (LSWI Landsat, annual, summer, `"reference": ["1985-01-01", "2025-12-31"]`) over the sectors;
   `time_series` of SOILM, CWD and PRECIP (TerraClimate, annual) over `sectores_clima.gpkg` (the 26-ha Comeya sector
   buffered by 3 km, as it gets no 4.6-km pixel); `compare_series` of LSWI Sentinel-2, `"step": "monthly"`,
   `"season": ["06-01", "09-30"]`, 2017-2025 against 2017 and against 2025.
8. Maps: `trend_map` of LSWI Landsat 1985-2025 (summer, harmonize, hamed-rao) over bboxes of Castro Laboreiro
   `[-8.2, 41.99, -8.05, 42.09]`, Mourela `[-7.97, 41.79, -7.86, 41.86]`, Comeya `[-5.003, 43.278, -4.974, 43.293]` and
   Sierra Nevada `[-3.45, 37.0, -3.15, 37.11]` (with `where` ELEVATION >= 2450 and WorldCover without water, built,
   trees); WAVI Sentinel-2 and late-winter NDVI Landsat over Castro Laboreiro.
9. Fire check of a dry year: `burn_severity` (Sentinel-2, dNBR) over `turberas.gpkg`, 2025-06-15/07-31 against
   2025-09-01/10-15, and the same windows of 2024 as the reference (`scripts/dnbr_2025.py`). Each took ~45 min with 134
   features: use a bbox and `perimeter: true` instead, or `find_burnt_areas`.
10. Priority index (`scripts/analisis.py`): within each park, mean of the percentile ranks of the Sen slope of LSWI
    Landsat (low = bad), the % of area with significant LSWI decrease, the Sen slope of LSWI Sentinel-2 and the Sen slope
    of late-winter NDVI Landsat (high = bad; not in Sierra Nevada).

## Results to expect
- LSWI Landsat 1985-2025: significant decrease in 4 of 134 peatlands (PG_GE_19, PG_GE_14, PG_GE_01, PG_GE_12), increase
  in 56; MSI increase (drier) in 7, decrease in 52; NDVI summer increase in 113; late-winter NDVI increase in 82 of 119
  (`analisis/tabla_turberas.csv`, from `tt_*`).
- Sector LSWI Landsat Sen: CL +0.0018/yr (p = 0.009), PS +0.0011 (p = 0.005), others not significant (`st_LSWI_L`).
- BACI peatland - ring (LSWI): MO -0.00065/yr (p < 0.001; 0.067 -> 0.049 from 1985-1999 to 2013-2025); CL +0.0009,
  GE +0.0006, SN +0.0012 (all p <= 0.001); PS and PE not significant (`analisis/baci_sectores.csv`). Late-winter NDVI
  BACI: CL +0.0011/yr (p = 0.005), MO not significant.
- Area drying (area-weighted): 11.5 % Peneda-Gerês, 0.2 % Picos, 4.8 % Sierra Nevada (`area_trend_LSWI_L_*`).
- Spearman LSWI ~ SOILM (detrended): 0.43 CL, 0.46 MO, 0.52 SN (`analisis/clima_correlacion.csv`); summer CWD Sen
  +0.29 to +0.41 mm/month per year, significant only in MO (`st_CWD`).
- 2025 vs 2017-2025 (Sentinel-2 LSWI): -0.07 to -0.10 in July-September in Castro Laboreiro (`cmp_LSWI_S2_2025`);
  dNBR > 0.27 over 25.7 ha in CL in 2025 vs 89.2 ha in 2024 (no general fire); PG_GE_17 97.5 % in 2025, 0 in 2024
  (`analisis/dnbr_2025_vs_2024.csv`).
- Top priority: PG_GE_19, PG_CL_10, PG_GE_04, PG_GE_14, PG_GE_01 (Peneda-Gerês); SN_B069, SN_B041, SN_B174 (Sierra Nevada).

## Pitfalls
- MSI and TCW are in MonitorEO >= 0.3.96 only (an older MCP server says they are not in the catalog); SPEI6 (SPEIbase, 0.5°) is in
  the catalog but was not used: SOILM and CWD of TerraClimate were used.
- The NDWI of MonitorEO is McFeeters' (green - NIR): it falls when vegetation greens, it is not a vegetation-water index;
  use LSWI (= Gao's NDWI) or MSI for moisture.
- Harmonized Landsat still rises from Landsat 5/7 to 8/9: read the peatland - ring difference, not the raw trend.
- `area_by_class` with `trend: true` over 134 features x 41 years exceeded memory; split by sector.
- TerraClimate gives no value for a 26-ha polygon (pixel 4.6 km): buffer it.
- `burn_severity` per feature over 134 polygons took ~45-50 min each; dNBR between July and September also rises with
  drought browning, so compare with a normal year.
- 134 per-peatland tests at p < 0.05 give about 3 chance "significant" trends per direction and index: trust the
  clustered ones confirmed per pixel (Gerês), not isolated Sentinel-2 ones (9 summers).
- ICNF 7140 polygons are habitat mosaics; summer-NDVI borreguiles are an approximation; no piezometers to calibrate.

## Sources and citations
- Peatland and wetland polygons: ICNF PSRN2000 habitats (WFS above); MITECO Inventario Español de Zonas Húmedas 2025,
  https://www.miteco.gob.es/content/dam/miteco/es/biodiversidad/servicios/banco-datos-naturaleza/iezh/IEZH_shp_2025.zip
- Burdun et al. (2020), https://doi.org/10.3390/rs12182936; Kalácska et al. (2018), https://doi.org/10.3390/rs10050687;
  Jussila et al. (2023), https://doi.org/10.1002/rse2.363; Gao (1996), https://doi.org/10.1016/S0034-4257(96)00067-3
  (verified with scite verify_papers).
- Cite MonitorEO (https://doi.org/10.5281/zenodo.23814894), Google Earth Engine (Gorelick et al., 2017,
  https://doi.org/10.1016/j.rse.2017.06.031) and the references and credits that each result returns
  (`<C02>/analisis/referencias_monitoreo.json`).

## Files
`<C02>/`: `informe.md` (report), `estado.json`, `llamadas.json`,
`llamadas/` (each answer and PNG), `monitoreo/` (CSV, PNG, GeoTIFF, README), `analisis/` (tables of this case),
`scripts/`, `fuentes/` (ICNF and IEZH data, `ORIGEN.txt`), and the zones `turberas.gpkg`, `sectores.gpkg`,
`sector_*.gpkg`, `turberas_*.gpkg`, `zonas_*.gpkg`.
