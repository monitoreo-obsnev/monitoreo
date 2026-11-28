---
name: monitoreo-disturbance-case-study
description: The method to study a disturbance (fire, frost, drought, pest, avalanche, windthrow, snowfall) and the recovery after it with the tools of MonitorEO, as the EVEREST case studies did in the Spanish and Portuguese mountain national parks - check the images, delimit the affected area with an official perimeter or burn_severity, build a control matched by elevation, measure severity, the reference dynamics, anomalies and trends, the recovery metrics of Marcos et al. (2023) with a BACI against the control, where it recovered on each pixel, and validate and cite. Use it before any new case study of a disturbance; the recipes everest-* are worked examples.
license: CC-BY-4.0
metadata:
  project: EVEREST (PID2023-151939OB-I00)
  kind: method
  monitoreo_version: "0.3.95"
---

# A case study of a disturbance and its recovery with MonitorEO

Worked examples: the recipes `everest-*` of this server (a fire, a frost, a dieback, an avalanche, in eight national
parks). Each step below names the tool of MonitorEO and the arguments that matter; the manual of MonitorEO (its wiki,
Concepts) explains each one.

## 0. Before computing
- Confirm the event in an official source or an article (date, place, area): civil protection, the park, Copernicus
  EMS, EFFIS, regional fire services. Never take a date or an area that a source does not give.
- Count the images: `image_count` with the variable, sensor and season you plan, step `annual` or `monthly`. Few
  valid observations (Landsat 5 in the 1990s, cloudy winters, snow) decide the sensor, the season and the period.
  Landsat has no images between 2012-05-05 and 2013-03-18 (`quality: {"landsat7": true}` fills it with stripes).

## 1. Affected area and control
- **An official perimeter** as the region, when there is one: `{"ems": "EMSR375"}` (Copernicus EMS, its grading or last
  delineation), `{"effis_id": ID}` (EFFIS; `find_burnt_areas` with the park or the country, the dates and
  `min_area_ha` gives the ids), `{"wfs": URL, "layer": ...}` (e.g. the burnt areas of ICNF) or `{"url": ...}` (a file
  on the web). Add `"within": {"wdpa_id": ...}` for the part inside the park.
- **A fire without a perimeter**: `burn_severity` with `perimeter: true` over a box around the fire (not only the park),
  a period before (about 3 months) and one after (1 to 3 months), Sentinel-2 from 2017-06 on and Landsat before;
  `largest: true` or `seed: [lon, lat]` keeps only the patch of the fire. In pastures and heath that dry between the
  two periods, `offset_region` (unburned land near the fire) subtracts the median dNBR of that land.
- **Other disturbances**: the area that the sources describe (a box, a circle around a point), refined with
  `compare_map` (after - before) or `compare_map` with `z: true` (the year of the disturbance against the variation
  of the years before).
- **Control**: `control_ring` with the affected area as the region (`gap` 150 m, `width` 1500 m by default;
  `exclude` other disturbances, e.g. `{"effis_id": [...]}`; `within` the park): a GeoPackage with `affected` and
  `control`, and a `where` that matches the pixels of both by elevation (percentiles 5 to 95 of the affected area). Add
  `ASPECT` to the `where` when the fire burned one slope. Or simply `ring: true` in `time_series` and
  `recovery_metrics`.
- Leave out the land covers that do not belong (water, built-up) with a `where` on a land cover map, e.g.
  `{"landcover": "CORINE", "year": 2018, "exclude": ["water", "built"]}`; split ecosystems with Dynamic World or CORINE.

## 2. Severity
- `burn_severity` dNBR (USGS classes, Key & Benson 2006), `index: "RdNBR"` with a period one year after the fire in the
  same season (Miller & Thode 2007 classes), `index: "RBR"`. Over the perimeter and inside the park.
- Contrast the area with the official one (% difference) and with an independent product: `area_by_class` of
  `MODIS/061/MCD64A1` or `ESA/CCI/FireCCI/5_1` band `BurnDate`, or `UMD/hansen/global_forest_change_2025_v1_13` band
  `lossyear`.

## 3. Reference dynamics, anomalies and trends
- `time_series` of the affected area and the control (or `ring: true`), monthly, with `min_coverage` (e.g. 0.5) so
  that the months with few clear pixels do not count; Landsat with `quality: {"harmonize": true}` for series that cross
  2013 (not for LST, SCF, SCD, SMOD, CF).
- `anomalies` (z of each step against the same part of the year in the years before the event, and the episodes of
  consecutive anomalous steps); `trend_table` / `trend_map` before and after the event (Mann-Kendall and Sen;
  `hamed-rao` for autocorrelated series). Read the difference affected - control: the change of Landsat sensor and the
  climate of the region move both.

## 4. Recovery
- `recovery_metrics` with the affected area and the control (or `ring: true`), the event date, monthly step and a
  reference of at least 3 years before it: S95, the impact (%, MADs), DIT, RRT (the recovery time), RET, the share
  recovered, the anomalies after the event and the trends before and after (Marcos et al. 2023, STL of Cleveland et
  al. 1990). Several affected areas and their controls at once: `pairs`.
- Several dimensions of the ecosystem: greenness (NDVI, EVI, Tasseled Cap greenness `TCG`), water (LSWI, MSI, `TCW`),
  energy (LST, ALBEDO), snow (SCD, SMOD), carbon (GPP of MODIS).
- `recovery_map` (annual, a season, small areas): where it recovered on each pixel.
- Structure, as context: `CANOPY_HEIGHT` (ETH 2020) and `TREE_COVER` (Hansen 2000) in `region_stats` or as zones.

## 5. Validation
A case is validated only if: a verified source names the event with its date and place; the abrupt change of the
affected area (tINF, the drop) is at the date of the event (±3 months for a pulse) and not in the control; the signal
is where the sources say; and the analysis is complete (severity or delimitation, reference dynamics, at least two
dimensions of the recovery with their metrics, compared with the literature). If the signal is not coherent after two
attempts, do not force the case.

## 6. Cite and record
- End every report with the references and credits that each result returns (MonitorEO, Google Earth Engine, the data,
  the methods, the region, the official perimeters), and the manual links of each variable.
- Keep every call (tool and arguments) and its answer: they make the recipe of the case. Write it as a skill (a folder
  with a SKILL.md: question, region and periods, the exact calls in order, the results to expect with the file of each
  number, the pitfalls, the sources) so that it can be repeated or adapted.

## References
- Marcos, B., Gonçalves, J., Alcaraz-Segura, D., Cunha, M., & Honrado, J. P. (2023). Assessing the resilience of
  ecosystem functioning to wildfires using satellite-derived metrics of post-fire trajectories. Remote Sensing of
  Environment, 286, 113441. https://doi.org/10.1016/j.rse.2022.113441
- Key, C. H., & Benson, N. C. (2006). Landscape assessment (LA): Sampling and analysis methods. USDA Forest Service,
  RMRS-GTR-164-CD.
- Miller, J. D., & Thode, A. E. (2007). Quantifying burn severity in a heterogeneous landscape with a relative version
  of the delta Normalized Burn Ratio (dNBR). Remote Sensing of Environment, 109(1), 66–80.
  https://doi.org/10.1016/j.rse.2006.12.006
- Cleveland, R. B., Cleveland, W. S., McRae, J. E., & Terpenning, I. (1990). STL: A seasonal-trend decomposition
  procedure based on loess. Journal of Official Statistics, 6(1), 3–73.
