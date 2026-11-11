# Needs the Python package monitoreo in the Python of reticulate (RETICULATE_PYTHON) and, for the tests with
# Earth Engine, EE_PROJECT.

skip_if_no_python <- function() {
  skip_if_not(reticulate::py_module_available("monitoreo"), "Python package monitoreo not available")
}

test_that("catalog and regions", {
  skip_if_no_python()
  v <- mo_variables(sensor = "Sentinel-2")
  expect_true(all(v$sensor == "Sentinel-2"))
  expect_true("NDVI" %in% v$variable)
  expect_equal(mo_describe("NDSI", "Modis")$measures, "snow")
  expect_equal(mo_describe("SCF", "Landsat")$metric, "mean")  # snow cover frequency: only the mean
  expect_equal(unlist(mo_describe("SCF", "Landsat")$fixed_filters), c("clouds", "water"))  # always, fixed
  expect_true(mo_describe("SLOPE", "Copernicus")$static)  # elevation and slope: fixed layers, without dates
  expect_error(mo_time_series(mo_bbox(-3.4, 37.0, -3.3, 37.1), "ELEVATION", "Copernicus", "2020-01-01", "2020-12-31"),
               "fixed layer, without dates")
  expect_error(mo_map_layer(mo_bbox(-3.4, 37.0, -3.3, 37.1), "SCF", "Landsat", "2020-10-01", "2021-05-31"),
               "only takes the metric 'mean'")
  # true colour: the variables of Sentinel-2 and Landsat and the cloud frequency of MODIS, refused before Earth Engine
  expect_true(isTRUE(v$rgb[v$variable == "NDVI"]))
  expect_true(mo_describe("NDVI", "Sentinel-2")$rgb)
  expect_false(mo_describe("NDVI", "Modis")$rgb)  # MOD13Q1 has no green band
  expect_error(mo_rgb_map(mo_bbox(-3.4, 37.0, -3.3, 37.1), "NDVI", "Modis", "2020-01-01", "2020-12-31"),
               "has no true colour")
  expect_error(mo_rgb_map(mo_bbox(-3.4, 37.0, -3.3, 37.1), "ELEVATION", "Copernicus"), "fixed layer")
  expect_error(mo_download_rgb(mo_bbox(-3.4, 37.0, -3.3, 37.1), "NDVI", "Sentinel-2", "2020-06-01", "2020-06-30",
                               tempfile(fileext = ".tif"), metric = "std"), "is not a colour")
  expect_error(mo_image(mo_bbox(-3.4, 37.0, -3.3, 37.1), "NDVI", "Modis", "2020-01-01", "2020-12-31", rgb = TRUE),
               "has no true colour")
  expect_equal(mo_bbox(-3.6, 36.8, -3.5, 36.9)$bbox[[3]], -3.5)
  expect_equal(mo_wdpa(c(1, 2))$wdpa_id, list(1L, 2L))
  expect_equal(mo_country("esp"), list(country = list("ESP")))
  expect_equal(mo_admin(141938, level = 2), list(admin2 = list(141938L)))
  expect_equal(mo_island(2.9, 39.6)$island_at, list(2.9, 39.6))
  expect_error(mo_admin(1, level = 3))
})

test_that("references", {
  out <- capture.output(refs <- mo_references())
  expect_length(refs, 2)
  expect_match(refs[1], "zenodo.23814894")
  expect_match(refs[2], "^Gorelick, N.*10.1016/j.rse.2017.06.031$")
  df <- monitoreo:::cited(data.frame(a = 1), list(references = list(list(text = "A. (2020). T. https://doi.org/1")),
                                                  credits = list("Credit")))
  expect_equal(capture.output(mo_references(df)), c("A. (2020). T. https://doi.org/1", "Credit"))
  expect_error(mo_references(data.frame(a = 1)), "no references")
  expect_match(paste(capture.output(mo_about()), collapse = " "), "Google Earth Engine: Planetary-scale")
  skip_if_no_python()
  d <- mo_describe("NDVI", "Sentinel-2")
  refs <- capture.output(mo_references(d))
  expect_true(any(grepl("^Tucker, C. J. \\(1979\\).*https://doi.org/10.1016/0034-4257\\(79\\)90013-0$", refs)))
  expect_true(any(grepl("Copernicus Sentinel data", refs)))
})

test_that("leaflet with several maps: the true colour, then the index on top", {
  skip_if_not_installed("leaflet")
  rgb <- list(url = "https://ee/rgb/{z}/{x}/{y}", bands = list("red", "green", "blue"), min = 0.0123, max = 0.2876,
              name = "NDVI Sentinel-2 | 2023-06-01 / 2023-08-31 (median), true colour")
  ndvi <- list(url = "https://ee/ndvi/{z}/{x}/{y}", min = 0.1, max = 0.8, palette = list("000080", "800000"),
               name = "NDVI Sentinel-2 | 2023-06-01 / 2023-08-31 (median)")
  calls <- function(m) vapply(m$x$calls, function(k) k$method, "")
  one <- mo_leaflet(ndvi)  # as before: one map, without control of layers
  expect_equal(calls(one), c("addProviderTiles", "addTiles"))
  expect_equal(one$x$calls[[2]]$args[[1]], ndvi$url)
  both <- mo_leaflet(rgb, ndvi)
  expect_equal(calls(both), c("addProviderTiles", "addTiles", "addControl", "addTiles", "addLayersControl"))
  expect_equal(both$x$calls[[2]]$args[[1]], rgb$url)
  expect_equal(both$x$calls[[3]]$args[[1]], "True colour (red, green, blue): reflectance from 0.0123 to 0.288")
  expect_equal(both$x$calls[[4]]$args[[1]], ndvi$url)
  expect_equal(unlist(both$x$calls[[5]]$args[[2]]), c(rgb$name, ndvi$name))
  expect_equal(mo_leaflet(list(rgb, ndvi))$x$calls, both$x$calls)  # a list of maps, the same
})

test_that("time series, statistics and map with Earth Engine", {
  skip_if_no_python()
  skip_if(Sys.getenv("EE_PROJECT") == "", "EE_PROJECT not set")
  mo_init()
  region <- mo_bbox(-3.62, 36.86, -3.50, 36.93)
  ts <- mo_time_series(region, "NDVI", "Sentinel-2", "2021-05-01", "2021-07-31")
  expect_equal(nrow(ts), 3)
  expect_s3_class(ts$date, "Date")
  expect_true(all(ts$value > 0 & ts$value < 1))
  expect_match(attr(ts, "title"), "NDVI Sentinel-2")
  expect_true(any(grepl("^Gorelick", attr(ts, "references"))) && any(grepl("Copernicus", attr(ts, "credits"))))
  expect_s3_class(mo_plot(ts), "ggplot")
  st <- mo_region_stats(region, "LST", "Modis", "2021-06-01", "2021-08-31", metric = "mean")
  expect_true(st$min <= st$max)
  m <- mo_map_layer(region, "NDVI", "Modis", "2021-01-01", "2021-12-31")
  expect_match(m$url, "^https://.*\\{z\\}")
  img <- mo_image(region, "NDVI", "Modis", "2021-01-01", "2021-12-31")
  expect_true(inherits(img$image, "ee.image.Image"))
})

test_that("regions from sf", {
  skip_if_no_python()
  skip_if_not_installed("sf")
  skip_if(Sys.getenv("EE_PROJECT") == "", "EE_PROJECT not set")
  mo_init()
  p <- sf::st_sfc(sf::st_polygon(list(rbind(c(445000, 4079000), c(449000, 4079000), c(449000, 4084000),
                                            c(445000, 4084000), c(445000, 4079000)))), crs = 25830)
  x <- sf::st_sf(zona = "oeste", geometry = p)
  ts <- mo_time_series(mo_sf(x, "zona"), "NDVI", "Sentinel-2", "2021-01-01", "2021-12-31", step = "annual")
  expect_equal(ts$region, "oeste")
})

test_that("download of a recipe and of a map", {
  skip_if_no_python()
  skip_if(Sys.getenv("EE_PROJECT") == "", "EE_PROJECT not set")
  mo_init()
  out <- tempfile()
  region <- mo_bbox(-3.62, 36.86, -3.50, 36.93)
  recipe <- list(study = list(resolution = 250), period = c("2021-01-01", "2021-12-31"),
                 variables = list(list(index = "NDVI", sensor = "Modis", metric = c("p5", "p95"))))
  plan <- mo_download_variables(recipe, region, out, dry_run = TRUE)
  expect_equal(plan$files[[2]]$file, "2_NDVI_MODIS_p95.tif")
  res <- mo_download_variables(recipe, region, out)
  expect_true(res$done)
  expect_true(all(file.exists(file.path(out, c("1_NDVI_MODIS_p5.tif", "2_NDVI_MODIS_p95.tif")))))
  img <- mo_download_image(region, "NDVI", "Modis", "2021-01-01", "2021-12-31", file.path(out, "ndvi.tif"),
                           resolution = 250)
  expect_equal(img$grid$crs, "EPSG:32630")
  expect_true(file.exists(img$file))
})

test_that("true colour with Earth Engine", {
  skip_if_no_python()
  skip_if(Sys.getenv("EE_PROJECT") == "", "EE_PROJECT not set")
  mo_init()
  region <- mo_bbox(-3.62, 36.86, -3.50, 36.93)
  x <- mo_download_rgb(region, "NDVI", "Sentinel-2", "2021-06-01", "2021-06-30", tempfile(fileext = ".tif"),
                       resolution = 60)
  expect_true(file.exists(x$file))
  expect_equal(unlist(x$bands), c("red", "green", "blue"))
  expect_equal(reticulate::import("osgeo.gdal")$Open(x$file)$RasterCount, 3)  # a GeoTIFF of three bands
  expect_equal(x$grid$crs, "EPSG:32630")
  expect_true(x$min < x$max)
  expect_null(x$palette)
  m <- mo_rgb_map(region, "NDVI", "Sentinel-2", "2021-06-01", "2021-06-30")
  expect_match(m$url, "^https://.*\\{z\\}")
  expect_match(m$name, "true colour$")
  expect_true(m$min < m$max)
  img <- mo_image(region, "NDVI", "Sentinel-2", "2021-06-01", "2021-06-30", rgb = TRUE)
  expect_equal(unlist(img$image$bandNames()$getInfo()), c("red", "green", "blue"))
  expect_equal(unlist(img$vis$bands), c("red", "green", "blue"))
})

test_that("seasonal trends and comparison of periods", {
  skip_if_no_python()
  skip_if(Sys.getenv("EE_PROJECT") == "", "EE_PROJECT not set")
  mo_init()
  region <- mo_bbox(-3.62, 36.86, -3.50, 36.93)
  tr <- mo_trend_table(region, "NDVI", "Modis", "2014-01-01", "2021-12-31", step = "annual")
  expect_equal(tr$key, "all")
  expect_equal(tr$n, 8)
  expect_equal(nrow(attr(tr, "yearly")), 8)
  cmp <- mo_compare_series(region, "NDVI", "Modis", "2016-01-01", "2018-12-31", "2021-01-01", "2021-12-31")
  expect_equal(nrow(cmp), 12)
  expect_equal(cmp$difference, cmp$other - cmp$reference)
  f <- tempfile(fileext = ".tif")
  d <- mo_download_trend(region, "NDVI", "Modis", "2014-01-01", "2021-12-31", f)
  expect_equal(unlist(d$bands), c("slope", "tau", "z", "p_value", "intercept", "n"))
})
