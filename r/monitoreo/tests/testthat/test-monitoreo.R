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
  expect_equal(mo_bbox(-3.6, 36.8, -3.5, 36.9)$bbox[[3]], -3.5)
  expect_equal(mo_wdpa(c(1, 2))$wdpa_id, list(1L, 2L))
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
