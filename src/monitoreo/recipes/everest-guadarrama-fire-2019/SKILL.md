---
name: everest-guadarrama-fire-2019
description: Wildfire of La Granja–Real Sitio de San Ildefonso (4 August 2019) in Sierra de Guadarrama National Park, in Scots pine forest and broom shrubland (piornal). Burned perimeter and dNBR/RdNBR severity with burn_severity (Sentinel-2 and Landsat), contrast with the Copernicus EMS EMSR375 perimeter, MCD64A1 and FireCCI51, a control ring on the same slope matched by elevation, monthly Landsat and Sentinel-2 series of NDVI, LSWI, LST and albedo split by ecosystem (Dynamic World), trends, and Marcos et al. (2023) recovery metrics with a BACI difference. Use it to repeat this case or to adapt it to a recent mountain fire with an official perimeter.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  park: Parque Nacional de la Sierra de Guadarrama
  wdpa_id: "555546231"
  event: "guadarrama_incendio_2019"
  event_date: "2019-08-04"
  disturbance: fire
  status: validated
  monitoreo_version: "0.3.86"
---

# Wildfire of La Granja–San Ildefonso, Sierra de Guadarrama, 2019

> **Files of this recipe.** `<everest>` is the folder of the EVEREST project where this case was computed: its
> zones (`resultados/<park>/*.gpkg`), its local scripts (`herramientas/`, `scripts/`) and its state files are not part of
> MonitorEO. To repeat the case, rebuild them with MonitorEO: the affected area from the official perimeter
> (`{"ems": ...}`, `{"effis_id": ...}`, `{"wfs": ...}`) or from `burn_severity` with `perimeter: true`, the control
> with `control_ring` (or `ring: true`), and the series and metrics with the calls marked «now». See
> `monitoreo-disturbance-case-study` for the method.

## Question
How much of the national park burned on 2019-08-04, how severely, and how far have the pine forest and the broom
shrubland recovered 7 years later in carbon, water and energy? It informs the follow-up of the emergency works and the
Junta de Castilla y León's replanting, and whether the pine forest is turning into shrubland
(estado/parques/guadarrama.json).

## Region and periods
- Affected area: Sentinel-2 perimeter from `burn_severity` with `perimeter: true` (dNBR ≥ 0.1, patches ≥ 1 ha),
  `<everest>/resultados/guadarrama/perimetro_s2_incendio.gpkg` (418.0 ha; inside/outside
  the park in `perimetro_s2_incendio_parque.gpkg`). Official perimeter: EMSR375 vectors downloaded to
  `resultados/guadarrama/fuentes/` and `perimetro_emsr375.gpkg`; «now» use `{"ems": "EMSR375"}` directly.
- Control: ring 150–1650 m around the Sentinel-2 perimeter built **locally** with `herramientas/zonas.py`, clipped to
  the west-facing slope (aspect 180°–330°, `scripts/control_orientacion.py`) and to the park:
  `zonas_v2.gpkg` (regions `afectada`, `control`; 1405.6 ha of control, 587.4 ha in the park). A first ring
  (`zonas.gpkg`, including the Madrid slope) was discarded.
- where: elevation p5–p95 of the affected zone, plus Dynamic World 2018 to split the ecosystems:
  - pine (**Wp**): `[{"variable":"ELEVATION","sensor":"Copernicus","min":1698,"max":2094},{"landcover":"DynamicWorld","year":2018,"exclude":["water","grassland","wetland","cropland","shrubland","built","bare","snow"]}]`
  - broom (**Wb**): same elevation and `{"landcover":"DynamicWorld","year":2018,"exclude":["trees","water","wetland","cropland","built","bare","snow"]}`
- Periods: pre-fire window 2019-07-01/08-03 vs post 2019-08-08/09-30 (and the 3-month windows 2019-05-15/08-02 vs
  08-15/10-15); RdNBR one year later 2020-07-01/08-31; series Landsat 1985-01 → 2026-10, Sentinel-2 2017-03-28 → 2026-10.
- Sensors: Sentinel-2 for the perimeter and severity (2.3 years of pre-fire reference only); Landsat for the long
  reference (1985–2019); MODIS NDVI computed on the first zones but not analysed (≈60 pixels of 250 m).

## Steps
Run with `herramientas/mcp_calls.py guadarrama resultados/guadarrama/llamadas.json` (74 calls). **Z** =
`{"file": "<everest>/resultados/guadarrama/zonas_v2.gpkg", "name_field": "region", "within": {"wdpa_id": 555546231}}`.

0. «now», not run: `{"tool": "image_count", "args": {"region": Z, "variable": "NDVI", "sensor": "Sentinel-2", "start": "2017-03-28", "end": "2019-08-03", "step": "monthly"}}` to see the short pre-fire Sentinel-2 record.
1. Perimeter and dNBR (box around the fire, then the whole park):
   `{"tool": "burn_severity", "args": {"region": {"bbox": [-4.01, 40.86, -3.92, 40.93]}, "sensor": "Sentinel-2", "start": "2019-07-01", "end": "2019-08-03", "other_start": "2019-08-08", "other_end": "2019-09-30", "perimeter": true}}`
   repeated with the 3-month windows, with `"sensor": "Landsat"`, and with `{"wdpa_id": 555546231}`. «now» add
   `"largest": true` (or `"seed": [-3.964, 40.894]`) to keep only this fire.
2. Severity inside/outside the park and inside EMSR375:
   `{"tool": "burn_severity", "args": {"region": {"file": "<everest>/resultados/guadarrama/perimetro_s2_incendio_parque.gpkg", "name_field": "region"}, "sensor": "Sentinel-2", "start": "2019-07-01", "end": "2019-08-03", "other_start": "2019-08-08", "other_end": "2019-09-30"}}`;
   RdNBR: same with `"index": "RdNBR", "other_start": "2020-07-01", "other_end": "2020-08-31"`.
   «now» the official perimeter as region: `{"region": {"ems": "EMSR375", "within": {"wdpa_id": 555546231}}, ...}`.
3. Independent burned-area products (dates and hectares):
   `{"tool": "area_by_class", "args": {"region": {"file": ".../perimetro_s2_incendio.gpkg", "name_field": "region"}, "collection": "MODIS/061/MCD64A1", "band": "BurnDate", "start": "2019-08-01", "end": "2019-09-30", "metric": "max", "breaks": [1, 213, 230]}}`,
   the same with `"collection": "ESA/CCI/FireCCI/5_1"` and with the bbox; `region_stats` with `"stats": ["min", "p50", "max"]` for the burn dates.
4. Land cover and matching checks: `area_by_class` with `{"landcover": "DynamicWorld", "year": 2018}` and CORINE 2018 on
   Z; `region_stats` of ELEVATION and of `{"image": "COPERNICUS/DEM/GLO30_2024_1", "band": "DEM", "terrain": "aspect"}`;
   summer 2018 NDVI (Sentinel-2, 2018-06-15/09-15) per ecosystem.
   «now» the control in one call:
   `{"tool": "control_ring", "args": {"region": {"file": "<everest>/resultados/guadarrama/perimetro_s2_incendio.gpkg", "name_field": "region"}, "gap": 150, "width": 1500, "within": {"wdpa_id": 555546231}}}`
   and add `{"variable": "ASPECT", "sensor": "Copernicus", "min": 180, "max": 330}` to the where it returns (replaces
   `control_orientacion.py`).
5. Monthly series per ecosystem (NDVI, LSWI, LST, ALBEDO with Landsat; NDVI, LSWI, ALBEDO with Sentinel-2 at 20 m):
   `{"tool": "time_series", "args": {"region": Z, "variable": "NDVI", "sensor": "Landsat", "start": "1985-01-01", "end": "2026-10-31", "step": "monthly", "scale": 30, "where": Wp}}`
   and with Wb; NDVI without the land-cover condition (`todo`). «now» add `"min_coverage": 0.5` (replaces
   `scripts/filtrar_cobertura.py`) or `"ring": true` with the perimeter as region.
6. Reference dynamics: `trend_table` 1985–2018 and 2020–2026 (annual, `"season": ["06-01", "09-30"]`);
   `compare_series` 2013-04-01/2019-07-31 vs 2020-08-01/2026-07-31 (monthly); per-pixel trend:
   `{"tool": "area_by_class", "args": {"region": Z, "variable": "NDVI", "sensor": "Sentinel-2", "start": "2020-01-01", "end": "2026-10-31", "trend": true, "step": "annual", "season": ["06-01", "09-30"], "where": Wp}}`.
7. Snow (exploratory): `time_series` annual SCD (`"metric": "days"`) and SMOD (`"metric": "melt"`), Landsat and Sentinel-2, Wp and Wb.
   Climate: `time_series` PRECIP (sum) and TMEAN of ERA5-Land, 2000–2025, annual.
8. Recovery metrics: **local** `herramientas/metricas_recuperacion.py` (`scripts/metricas.sh`, event 2019-08-04,
   3 reference years). «now»:
   `{"tool": "recovery_metrics", "args": {"region": {"file": "<everest>/resultados/guadarrama/zonas_v2.gpkg", "name_field": "region", "within": {"wdpa_id": 555546231}}, "affected": "afectada", "control": "control", "variable": "NDVI", "sensor": "Landsat", "start": "2013-04-01", "end": "2026-10-31", "event": "2019-08-04", "step": "monthly", "reference_years": 3, "min_coverage": 0.5, "where": Wp}}`
   for each variable, sensor and ecosystem; then `recovery_map` (`"season": ["06-01", "09-30"]`, `"resolution": 30`) on the perimeter.

## Results to expect
From estado/parques/guadarrama.json, `superficies_perimetros.csv` and `metricas_resumen.csv`:
- Burned 418.0 ha (Sentinel-2), 298.8 ha in the park (71.5 %); 415.6 / 300.2 ha with 3-month windows; 414.4 / 296.7 ha
  with Landsat. Official: 400.88 ha (Consejo de Ministros, +4.3 %); EMSR375 grading 370.2 ha (271.6 ha in the park),
  delineation 351.3 ha (260.7). 99.7 % of the grading inside the Sentinel-2 perimeter, IoU 0.88.
- dNBR in the park: 26.4 ha low, 26.2 moderate-low, 71.0 moderate-high, 174.9 high (82.4 % moderate-high or high).
  RdNBR (one year): 251.8 of 299.0 ha high (84.2 %). Cover in the park: 164.0 ha trees (54.9 %), 132.2 ha shrub.
- MCD64A1: 298.2 ha inside the perimeter, 2019-08-03 to 08-11; FireCCI51: 330.7 ha, 2019-08-05 to 08-14.
- NDVI summer (compare_series): pine 0.615 → 0.361, control 0.617 → 0.645; broom 0.511 → 0.353, control 0.492 → 0.512.
- Difference affected − control (Landsat): impact NDVI −42.6 MAD (pine) and −40.4 (broom); LSWI −83.9 and −56.9;
  recovered in the last year NDVI 30.1 % / 31.0 %, LSWI 50.3 % / 58.2 %, LST 79.1 % / 86.8 %; no RRT for NDVI or LSWI.
  LST difference RRT 7.16 years (pine). Albedo crossed the reference (RRT dif 0.83–1.16 years) and became brighter
  than the control (+0.02–0.05): a change of structure, not a recovery.
- Snow: no detectable change against the control (Mann-Whitney p ≥ 0.07).

## Pitfalls
- Sentinel-2 has only 2.3 years before the fire: its z values (−20 to −111) are not interpretable; use Landsat's.
- Dynamic World 2018 and CORINE 2018 disagree (55 % vs 4 % trees in the burned park area): check with PNOA orthophotos.
- The first ring included the Madrid slope; the control had to be clipped by aspect to the same west-facing slope.
- The park-wide `burn_severity` found a second, uninventoried fire (Miraflores de la Sierra, 277.8 ha, 201.1 in the
  park, 13 km away): use `largest` or `seed` so it does not enter the perimeter.
- Months with < 50 % valid pixels removed; 54 % of Landsat months and 3 % of Sentinel-2 months were interpolated.
- The series mix natural recovery and the replanting (2020–2025) whose polygons are not available.
- A possible older disturbance: the pine of the affected zone had 0.05–0.08 less summer NDVI than the control in 1995–2003.

## Sources and citations
- Copernicus EMS EMSR375: https://mapping.emergency.copernicus.eu/activations/EMSR375 (vectors:
  https://cems-mapping-website.s3.eu-west-1.amazonaws.com/static/activations/EMSR375/EMSR375_AOI01_GRA_PRODUCT_r1_RTP01_v1_vector.zip
  and `..._DEL_PRODUCT_...`); Consejo de Ministros 2019-08-30:
  https://www.lamoncloa.gob.es/consejodeministros/Paginas/enlaces/300819-incendios.aspx
- Independent products: MCD64A1, doi:10.5067/MODIS/MCD64A1.061; FireCCI51, Lizundia-Loiola et al. 2020, doi:10.1016/j.rse.2019.111493.
- Method: Marcos et al. 2023, doi:10.1016/j.rse.2022.113441; Miller & Thode 2007, doi:10.1016/j.rse.2006.12.006;
  Howe et al. 2022, doi:10.3390/rs14205249; Fernández-García et al. 2018, doi:10.3390/rs10050733; Peña-Molina et al.
  2024, doi:10.3390/rs16101718; Martín-Ortiz et al. 2026, doi:10.3390/rs18091352; Viedma et al. 2020, doi:10.1016/j.rse.2020.111891.
- Ecology: Fernández Santos & Gómez Gutiérrez 1994, doi:10.2307/3235972; Fernández-Guisuraga et al. 2022,
  doi:10.3390/rs14205138; Jimeno-Llorente et al. 2023, doi:10.3390/fire6120450; Mantero et al. 2023,
  doi:10.1186/s42408-023-00182-7; Viana-Soto et al. 2020, doi:10.3390/rs12091499; Baudena et al. 2020, doi:10.1111/nph.16252.
- Cite MonitorEO (doi:10.5281/zenodo.23814894), Google Earth Engine (doi:10.1016/j.rse.2017.06.031) and the references
  and credits that each result returns (listed in `referencias_monitoreo` and `creditos` of the park json).

## Files
- `<everest>/resultados/guadarrama/`: `llamadas.json`, `llamadas/`, `monitoreo/`,
  `perimetro_*.gpkg`, `zonas_v2.gpkg`, `superficies_perimetros.csv`, `metricas_*.json/png`, `metricas_resumen.csv`,
  `mapa_severidad_dnbr_s2.png`, `scripts/`, `fuentes/` (EMSR375 zips, ORIGEN.txt).
- State: `estado/parques/guadarrama.json`; report `informe_perturbaciones.html`. Not published in the viewer (not recorded).
- Pending: replanting polygons from the Junta; official perimeter of Miraflores; EFFIS and Senf & Seidl (2021) checks;
  repeat in 2027.
