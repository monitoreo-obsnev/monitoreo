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

test_that("the land cover maps of the land cover masks, without Earth Engine", {
  skip_if_no_python()
  lc <- mo_landcover_maps()
  expect_s3_class(lc$classes, "data.frame")
  expect_true(all(c("water", "built", "cropland") %in% lc$classes$key))
  keys <- vapply(lc$maps, function(m) m$key, "")
  expect_true(all(c("WorldCover", "DynamicWorld", "CORINE", "MODIS") %in% keys))
  corine <- lc$maps[[which(keys == "CORINE")]]
  expect_true(any(grepl("^511 ", corine$classes$water)))
  expect_match(mo_landcover_maps("es")$classes$name[lc$classes$key == "water"], "Agua")
  expect_true(length(lc$references) > 0)
})

test_that("the GEE Community Catalog by its themes, without Earth Engine", {
  skip_if_no_python()
  th <- mo_community_themes()
  expect_s3_class(th, "data.frame")
  expect_equal(names(th), c("theme", "name", "datasets"))
  expect_true(all(th$datasets > 0))
  es <- mo_community_themes("es")
  expect_equal(es$theme, th$theme)  # the names of the catalog, for mo_community(), in any language
  expect_equal(es$name[es$theme == "Hydrology"], "Hidrología")
  dem <- mo_community(text = "fabdem")
  expect_equal(dem$id, "projects/sat-io/open-datasets/FABDEM")
  expect_equal(dem$type, "image_collection")
  expect_match(dem$docs, "^https://gee-community-catalog.org/")
  fire <- mo_community("incendios")  # a theme by a part of its name in Spanish
  expect_true(nrow(fire) > 0 && all(fire$theme == "Fire Monitoring and Analysis"))
  img <- mo_community(kind = "image", limit = 5)
  expect_equal(nrow(img), 5)
  expect_true(all(img$type == "image"))
  expect_equal(nrow(mo_community(theme = "Hydrology", text = "no dataset has these words")), 0)
  expect_error(mo_community("mountains"), "unknown theme")
  expect_error(mo_community(kind = "table"), "unknown kind")
  # the two themes of the menus without variables of the catalog point to these functions, in the words of R (its
  # functions and arguments), not those of the services, the MCP server or the command line
  themes <- list(community = "mo_community_themes() lists its themes and mo_community() their datasets",
                 earth_engine = "mo_asset(ID) describes it",
                 " Earth Engine data (by its ID) " = "mo_asset(ID) describes it")
  # its name in Spanish, in UTF-8 whatever the locale (a literal would not be read in UTF-8 in the locale C)
  themes[[paste0("Cat", intToUtf8(0xe1), "logo de la comunidad de GEE")]] <- "mo_community_themes() lists its themes"
  for (theme in names(themes)) {
    e <- tryCatch(mo_variables(theme = theme), error = identity)
    expect_s3_class(e, "simpleError")  # an error of R, before the services
    expect_match(conditionMessage(e), "has no variables of the catalog: ", fixed = TRUE)
    expect_match(conditionMessage(e), themes[[theme]], fixed = TRUE)
    expect_match(conditionMessage(e), "then compute it with its ID as collection (or image) and its band",
                 fixed = TRUE)
    expect_no_match(conditionMessage(e), "describe_asset|(?<!mo_)community_(themes|datasets)|collection=|--",
                    perl = TRUE)
  }
  expect_error(mo_variables(theme = "mountains"), "unknown theme")
  expect_true(nrow(mo_variables(theme = "climate")) > 0)
})

test_that("data of Earth Engine by its ID: the arguments reach the services by name", {
  calls <- list()
  answer <- function(tool) function(...) {
    calls[[tool]] <<- list(...)
    list(rows = list(), yearly = list(), profile = list(), title = tool, unit = "mm", references = list(),
         credits = list())
  }
  tools <- c("time_series", "time_series_to_drive", "map_layer", "region_stats", "export_image", "download_image",
             "trend_table", "trend_map", "download_trend", "compare_series", "compare_map", "download_comparison")
  local_mocked_bindings(services = function() stats::setNames(lapply(tools, answer), tools), .package = "monitoreo")
  region <- mo_bbox(-3.4, 37.0, -3.3, 37.1)
  pr <- list(collection = "IDAHO_EPSCOR/TERRACLIMATE", band = "pr", band_scale = 0.1, band_offset = 0,
             unit = "mm month-1")
  # with terrain, its unit is degree (the slope and the aspect are in degrees, whatever the band)
  bio <- list(image = "WORLDCLIM/V1/BIO", band = "bio01", band_scale = 0.1, band_offset = 0, unit = "degree",
              terrain = "slope")
  periods <- list(start = "1991-01-01", end = "2000-12-31", other_start = "2011-01-01", other_end = "2020-12-31")
  run <- function(f, ..., data) do.call(f, c(list(region, ...), data))
  run(mo_time_series, start = "2020-01-01", end = "2020-12-31", data = pr)
  run(mo_export_time_series, start = "2020-01-01", end = "2020-12-31", data = pr)
  run(mo_trend_table, start = "2001-01-01", end = "2020-12-31", data = pr)
  run(mo_trend_map, start = "2001-01-01", end = "2020-12-31", data = pr)
  run(mo_download_trend, start = "2001-01-01", end = "2020-12-31", path = "trend.tif", data = pr)
  run(mo_compare_series, data = c(periods, pr))
  run(mo_compare_map, data = c(periods, pr))
  run(mo_download_comparison, path = "comparison.tif", data = c(periods, pr))
  run(mo_map_layer, data = bio)
  run(mo_region_stats, data = bio)
  run(mo_export_image, data = bio)
  run(mo_download_image, path = "bio01.tif", data = bio)
  expect_setequal(names(calls), tools)
  for (tool in tools) {
    sent <- calls[[tool]]
    data <- if (tool %in% c("map_layer", "region_stats", "export_image", "download_image")) bio else pr
    expect_equal(sent[names(data)], data, info = tool)  # by name
    expect_null(sent[[2]])  # variable and sensor (by position, as before): None
    expect_null(sent[[3]])
  }
  expect_true("image" %in% names(calls$time_series) && is.null(calls$time_series[["image"]]))
  expect_false("terrain" %in% names(calls$trend_table))  # only where an image can be computed
  # the calls of the variables of the catalog, by position, as before
  mo_time_series(region, "NDVI", "Modis", "2020-01-01", "2020-12-31", "annual")
  expect_equal(unname(calls$time_series[1:6]), list(region, "NDVI", "Modis", "2020-01-01", "2020-12-31", "annual"))
  expect_null(calls$time_series[["band"]])
  mo_map_layer(region, "ELEVATION", "Copernicus")
  expect_equal(unname(calls$map_layer[1:5]), list(region, "ELEVATION", "Copernicus", NULL, NULL))
  # neither a variable nor data of Earth Engine, or both mixed: a clear error before Python (the words of the MCP
  # server and the command line), and nothing sent to the services
  calls <- list()
  expect_error(mo_time_series(region, start = "2020-01-01", end = "2020-12-31"),
               "give variable and sensor (a variable of the catalog: mo_variables()), or collection or image and band",
               fixed = TRUE)
  expect_error(mo_time_series(region, "NDVI", start = "2020-01-01", end = "2020-12-31"), "give the sensor of NDVI")
  # an ID of Earth Engine given as the variable (no variable of the catalog has a '/'), with a sensor or without:
  # neither its sensor asked for nor called a variable of the catalog
  not_variable <- paste("IDAHO_EPSCOR/TERRACLIMATE is not a variable of the catalog (mo_variables()): give an ID of",
                        "Earth Engine as collection or image (mo_asset() says which), with band, instead of variable")
  expect_error(mo_time_series(region, "IDAHO_EPSCOR/TERRACLIMATE", start = "2020-01-01", end = "2020-12-31"),
               not_variable, fixed = TRUE)
  expect_error(mo_time_series(region, "IDAHO_EPSCOR/TERRACLIMATE", band = "pr", start = "2020-01-01",
                              end = "2020-12-31"), not_variable, fixed = TRUE)
  expect_error(mo_map_layer(region, "IDAHO_EPSCOR/TERRACLIMATE", "TerraClimate", "2020-01-01", "2020-12-31"),
               not_variable, fixed = TRUE)
  expect_error(mo_trend_table(region, "IDAHO_EPSCOR/TERRACLIMATE", "TerraClimate", "2001-01-01", "2020-12-31",
                              collection = "IDAHO_EPSCOR/TERRACLIMATE", band = "pr"), not_variable, fixed = TRUE)
  expect_error(mo_image(region, "projects/sat-io/open-datasets/FABDEM", image = "projects/sat-io/open-datasets/FABDEM",
                        band = "b1", terrain = "slope"), "FABDEM is not a variable of the catalog", fixed = TRUE)
  expect_error(mo_map_layer(region, "NDVI", "Modis", "2020-01-01", "2020-12-31", image = "WORLDCLIM/V1/BIO",
                            band = "bio01"), "image, band: only for the data of Earth Engine given by its ID")
  expect_error(mo_region_stats(region, "ELEVATION", "Copernicus", terrain = "slope"), "^terrain: only for the data")
  expect_error(mo_map_layer(region, "NDVI", "Modis", "2020-01-01", "2020-12-31", unit = "1"),
               "NDVI is a variable of the catalog, with its own band, scale and unit")
  expect_error(do.call(mo_time_series, c(list(region, sensor = "Modis", start = "2020-01-01", end = "2020-12-31"), pr)),
               "sensor is for the variables of the catalog")
  expect_error(mo_map_layer(region, collection = "IDAHO_EPSCOR/TERRACLIMATE", image = "WORLDCLIM/V1/BIO",
                            band = "bio01"), "give collection (a collection of images with dates) or image", fixed = TRUE)
  expect_error(mo_trend_table(region, collection = "IDAHO_EPSCOR/TERRACLIMATE", start = "2001-01-01",
                              end = "2020-12-31"), "give band: the band of IDAHO_EPSCOR/TERRACLIMATE")
  expect_error(mo_download_image(region, collection = "IDAHO_EPSCOR/TERRACLIMATE", band = "pr", start = "2020-01-01",
                                 end = "2020-12-31", path = "pr.tif", terrain = "slope"), "terrain is for an image")
  expect_length(calls, 0)
})

test_that("several bands of the data by their ID: combined with band_reducer, with the errors of the package", {
  calls <- list()
  answer <- function(tool) function(...) {
    calls[[tool]] <<- list(...)
    list(rows = list(), yearly = list(), profile = list(), title = tool, unit = "mm", references = list(),
         credits = list())
  }
  tools <- c("time_series", "map_layer", "region_stats", "download_image", "trend_table", "compare_series")
  local_mocked_bindings(services = function() stats::setNames(lapply(tools, answer), tools), .package = "monitoreo")
  region <- mo_bbox(-3.4, 37.0, -3.3, 37.1)
  mo_time_series(region, collection = "IDAHO_EPSCOR/TERRACLIMATE", band = c("aet", "def"), band_reducer = "sum",
                 band_scale = 0.1, unit = "mm", start = "2020-01-01", end = "2020-12-31")
  expect_equal(calls$time_series[c("band", "band_reducer", "band_scale")],
               list(band = c("aet", "def"), band_reducer = "sum", band_scale = 0.1))
  mo_region_stats(region, image = "WORLDCLIM/V1/BIO", band = "bio05, bio06", band_reducer = "mean")
  expect_equal(calls$region_stats[c("band", "band_reducer")], list(band = "bio05, bio06", band_reducer = "mean"))
  mo_map_layer(region, collection = "IDAHO_EPSCOR/TERRACLIMATE", band = "pr", start = "2020-01-01",
               end = "2020-12-31")
  expect_true("band_reducer" %in% names(calls$map_layer) && is.null(calls$map_layer[["band_reducer"]]))
  calls <- list()
  # the words and the order of monitoreo.variable.check_bands
  expect_error(mo_trend_table(region, collection = "IDAHO_EPSCOR/TERRACLIMATE", band = c("aet", "def"),
                              start = "2001-01-01", end = "2020-12-31"),
               paste("IDAHO_EPSCOR/TERRACLIMATE: give band_reducer, 'sum' or 'mean', to combine its 2 bands (aet, def)",
                     "into one value on each pixel"), fixed = TRUE)
  expect_error(mo_map_layer(region, collection = "IDAHO_EPSCOR/TERRACLIMATE", band = "pr", band_reducer = "sum",
                            start = "2020-01-01", end = "2020-12-31"),
               "band_reducer combines several bands: give two or more in band (a list, or a text with commas)",
               fixed = TRUE)
  expect_error(mo_map_layer(region, collection = "IDAHO_EPSCOR/TERRACLIMATE", band = "aet,def",
                            band_reducer = "median", start = "2020-01-01", end = "2020-12-31"),
               "unknown band_reducer median: use sum, mean", fixed = TRUE)
  expect_error(mo_region_stats(region, image = "WORLDCLIM/V1/BIO", band = c("bio05", "bio05"), band_reducer = "mean"),
               "band bio05 is given twice: give each band once", fixed = TRUE)
  expect_error(mo_download_image(region, image = "COPERNICUS/DEM/GLO30", band = c("DEM", "edm"), terrain = "slope",
                                 path = "x.tif"),
               "terrain is the slope or the aspect of one band (an elevation): give one band, without band_reducer",
               fixed = TRUE)
  expect_error(mo_map_layer(region, "NDVI", "Modis", "2020-01-01", "2020-12-31", band_reducer = "sum"),
               "band_reducer: only for the data of Earth Engine given by its ID")
  expect_error(mo_time_series(region, collection = "IDAHO_EPSCOR/TERRACLIMATE", band = " , ", start = "2020-01-01",
                              end = "2020-12-31"),
               "give band: the band of IDAHO_EPSCOR/TERRACLIMATE (one, or several with band_reducer", fixed = TRUE)
  expect_length(calls, 0)
})

test_that("the statistics of the region, also the coefficient of variation, of the images and between the years", {
  sent <- NULL
  answer <- function(...) {
    sent <<- list(...)
    list(rows = list(list(region = "park", mean = 450, cv = 18.5, p90 = 610, n_pixels = 900L)),
         stats = list("mean", "cv", "p90"), title = "PRECIP TerraClimate", unit = "[%]", scale = 4000,
         references = list(), credits = list())
  }
  local_mocked_bindings(services = function() list(region_stats = answer), .package = "monitoreo")
  region <- mo_bbox(-3.4, 37.0, -3.3, 37.1)
  x <- mo_region_stats(region, "PRECIP", "TerraClimate", "2001-01-01", "2020-12-31", metric = "sum",
                       temporal = "annual", interannual = "cv", stats = c("mean", "cv", "p90"))
  expect_equal(sent[["interannual"]], "cv")
  expect_equal(sent[["stats"]], list("mean", "cv", "p90"))  # a list, also with one statistic
  expect_equal(x$cv, 18.5)
  expect_equal(attr(x, "unit"), "[%]")
  mo_region_stats(region, "NDVI", "Modis", "2020-01-01", "2020-12-31", stats = "cv")
  expect_equal(sent[["stats"]], list("cv"))
  mo_region_stats(region, "ELEVATION", "Copernicus")
  expect_null(sent[["stats"]])  # those of the package: mean, std, cv, min, p5, p50, p95 and max
  expect_equal(sent[["interannual"]], "mean")
})

test_that("mo_image of data of Earth Engine by its ID: its name, and the arguments sent by name", {
  skip_if_no_python()
  # the spec, kind and is_static of Python, without Earth Engine; the image, its colour ramp and pixel size faked
  real <- reticulate::import("monitoreo.services", convert = TRUE)
  variables <- reticulate::import("monitoreo.variable", convert = TRUE)
  real_import <- reticulate::import
  sent <- list()
  s <- list(make_spec = real$make_spec, variable_entry = real$variable_entry, composite_image = function(...) {
    sent$composite_image <<- list(...)
    list("image", list(geometry = function() "geometry"))
  })
  modules <- list(
    monitoreo.maps = list(vis_params = function(...) list(min = 0, max = 1), rgb_vis = function(...) list()),
    monitoreo.variable = list(kind = variables$kind, is_static = variables$is_static, check_rgb = variables$check_rgb,
                              data_name = variables$data_name, native_scale = function(spec) 30),
    monitoreo.references = list(cite = function(tool, args) {
      sent$cite <<- args
      list(references = list(), credits = list())
    }))
  local_mocked_bindings(services = function() s, .package = "monitoreo")
  local_mocked_bindings(import = function(module, ...) if (module %in% names(modules)) modules[[module]] else
    real_import(module, ...), .package = "reticulate")
  region <- mo_bbox(-3.4, 37.0, -3.3, 37.1)
  bio <- mo_image(region, image = "WORLDCLIM/V1/BIO", band = "bio01", band_scale = 0.1, unit = "degC")
  expect_equal(bio$name, "WORLDCLIM/V1/BIO bio01")  # a fixed image: no metric nor period
  data <- list(image = "WORLDCLIM/V1/BIO", band = "bio01", band_scale = 0.1, unit = "degC")
  expect_equal(sent$composite_image[names(data)], data)
  expect_null(sent$composite_image[[2]])  # variable and sensor: None
  expect_null(sent$composite_image[[3]])
  expect_equal(sent$cite[names(data)], data)  # cited as those data
  slope <- mo_image(region, image = "ee.ImageCollection('projects/sat-io/open-datasets/FABDEM')", band = "b1",
                    terrain = "slope")
  expect_equal(slope$name, "projects/sat-io/open-datasets/FABDEM b1 slope")
  # several bands combined on each pixel: the reducer and the bands, sent as a list with band_reducer
  both <- mo_image(region, image = "WORLDCLIM/V1/BIO", band = c("bio05", "bio06"), band_reducer = "mean",
                   band_scale = 0.1, unit = "degC")
  expect_equal(both$name, "WORLDCLIM/V1/BIO mean of bio05, bio06")
  expect_equal(sent$composite_image[c("band", "band_reducer")], list(band = c("bio05", "bio06"), band_reducer = "mean"))
  pr <- mo_image(region, collection = "IDAHO_EPSCOR/TERRACLIMATE", band = "pr", start = "2020-01-01",
                 end = "2020-12-31", metric = "sum", unit = "mm")
  expect_equal(pr$name, "IDAHO_EPSCOR/TERRACLIMATE pr sum 2020-01-01 2020-12-31")
  expect_equal(sent$composite_image$collection, "IDAHO_EPSCOR/TERRACLIMATE")
  # the variables of the catalog, as before; their fixed layers without metric nor period
  expect_equal(mo_image(region, "NDVI", "Modis", "2020-01-01", "2020-12-31")$name,
               "NDVI Modis median 2020-01-01 2020-12-31")
  expect_equal(mo_image(region, "ELEVATION", "Copernicus")$name, "ELEVATION Copernicus")
})

test_that("data of Earth Engine by its ID: clear errors before Earth Engine", {
  skip_if_no_python()
  region <- mo_bbox(-3.4, 37.0, -3.3, 37.1)
  bio <- "WORLDCLIM/V1/BIO"
  terraclimate <- "IDAHO_EPSCOR/TERRACLIMATE"
  # a fixed image has no dates: maps and their statistics, but no series, trends or comparisons
  expect_error(mo_time_series(region, image = bio, band = "bio01", start = "2020-01-01", end = "2020-12-31"),
               "given as a fixed image, without dates")
  expect_error(mo_trend_table(region, image = bio, band = "bio01", start = "2001-01-01", end = "2020-12-31"),
               "without dates")
  expect_error(mo_compare_series(region, image = bio, band = "bio01", start = "1991-01-01", end = "2000-12-31",
                                 other_start = "2011-01-01", other_end = "2020-12-31"), "without dates")
  expect_error(mo_map_layer(region, collection = terraclimate, band = "pr", start = "2020-01-01", end = "2020-12-31",
                            unit = "mm/día"), "UDUNITS")
  # the slope and the aspect are in degrees, whatever the unit of the band (the m of a DEM, that mo_asset() gives in its
  # arguments): another unit is refused, before Earth Engine
  expect_error(mo_map_layer(region, image = "USGS/SRTMGL1_003", band = "elevation", unit = "m", terrain = "slope"),
               "the slope of USGS/SRTMGL1_003 is in degrees", fixed = TRUE)
  # only the variables of the catalog have a true colour
  expect_error(mo_image(region, collection = terraclimate, band = "pr", start = "2020-01-01", end = "2020-12-31",
                        rgb = TRUE), "only the variables of the catalog")
})

test_that("burn severity with the RdNBR: its arguments reach the services, its classes and statistics come back", {
  args <- formals(mo_burn_severity)
  expect_true(all(c("index", "collection") %in% names(args)))
  expect_equal(args$index, "dNBR")  # as before
  expect_null(args$collection)
  sent <- NULL
  cls <- function(c, label, low, high, ha) list(region = "fire", class = c, label = label, rdnbr_min = low,
                                                rdnbr_max = high, ha = ha)
  answer <- list(
    index = "RdNBR",
    classes = list(cls(0L, "Unchanged", NULL, 0.069, 10), cls(1L, "Low severity", 0.069, 0.316, 5),
                   cls(2L, "Moderate severity", 0.316, 0.641, 4), cls(3L, "High severity", 0.641, NULL, 1)),
    burned_ha = list(fire = 10),
    stats = list(list(region = "fire", mean = 0.21, median = 0.18, p10 = -0.02, p90 = 0.55, min = -0.3, max = 1.1,
                      ha = 20)),
    title = "Burn severity (RdNBR, Miller & Thode 2007) Modis (median) | before 2022-06-01 / 2022-08-31, after ...",
    file = "rdnbr.tif", readme = "rdnbr.README.md",
    references = list(list(text = "Miller, J. D., & Thode, A. E. (2007). https://doi.org/10.1016/j.rse.2006.12.006")),
    credits = list())
  legend_of <- NULL
  local_mocked_bindings(services = function() list(burn_severity = function(...) {
    sent <<- list(...)
    answer
  }), burn_legend = function(index) {
    legend_of <<- index
    data.frame(value = 0:3, label = c("Unchanged", "Low severity", "Moderate severity", "High severity"))
  }, .package = "monitoreo")
  region <- mo_bbox(-3.0, 36.9, -2.9, 37.0)
  x <- mo_burn_severity(region, "2022-06-01", "2022-08-31", "2023-06-01", "2023-08-31", sensor = "Modis",
                        index = "RdNBR", collection = "MODIS/061/MYD09GA")
  expect_equal(unname(sent[1:7]), list(region, "Modis", "2022-06-01", "2022-08-31", "2023-06-01", "2023-08-31",
                                       "median"))
  expect_equal(sent$index, "RdNBR")
  expect_equal(sent$collection, "MODIS/061/MYD09GA")
  expect_equal(names(x), c("region", "class", "label", "rdnbr_min", "rdnbr_max", "ha"))  # the classes
  expect_equal(x$label, c("Unchanged", "Low severity", "Moderate severity", "High severity"))
  expect_equal(x$rdnbr_min, c(NA, 0.069, 0.316, 0.641))
  expect_equal(attr(x, "burned_ha"), c(fire = 10))
  expect_equal(attr(x, "stats")$median, 0.18)  # and the statistics of the RdNBR
  expect_equal(legend_of, "RdNBR")
  expect_equal(nrow(attr(x, "legend")), 4)
  expect_match(attr(x, "title"), "RdNBR, Miller & Thode 2007", fixed = TRUE)
  expect_equal(attr(x, "file"), "rdnbr.tif")
  expect_match(attr(x, "references"), "10.1016/j.rse.2006.12.006", fixed = TRUE)
  # the dNBR and the RBR as before: no collection sent unless given, the RBR without classes, legend or stats
  answer <- list(index = "RBR", stats = answer$stats, title = "Relativized Burn Ratio (RBR)", references = list(),
                 credits = list())
  legend_of <- NULL
  rbr <- mo_burn_severity(region, "2022-06-01", "2022-08-31", "2023-06-01", "2023-08-31", index = "RBR")
  expect_null(sent$collection)
  expect_equal(sent[[2]], "Sentinel-2")
  expect_equal(names(rbr), c("region", "mean", "median", "p10", "p90", "min", "max", "ha"))
  expect_null(attr(rbr, "stats"))
  expect_null(attr(rbr, "legend"))
  expect_null(attr(rbr, "burned_ha"))
  expect_null(legend_of)
})

test_that("burn severity with the perimeter: its arguments reach the services, its polygons come back", {
  args <- formals(mo_burn_severity)
  expect_true(all(c("perimeter", "burned_min", "min_ha") %in% names(args)))
  expect_null(args$perimeter)  # as before: no perimeter unless asked for
  sent <- NULL
  answer <- list(index = "dNBR", classes = list(list(region = "fire", class = 1L, label = "Low severity",
                                                      dnbr_min = 0.1, dnbr_max = 0.27, ha = 5)),
                 burned_ha = list(fire = 5), title = "Burn severity (dNBR, USGS)", perimeter = "fire.gpkg",
                 perimeter_ha = list(fire = 4.5), perimeter_patches = list(fire = 2L), burned_min = 0.27,
                 min_ha = 2, references = list(), credits = list())
  local_mocked_bindings(services = function() list(burn_severity = function(...) {
    sent <<- list(...)
    answer
  }), burn_legend = function(index) data.frame(value = 1L, label = "Low severity"), .package = "monitoreo")
  x <- mo_burn_severity(mo_bbox(-3.0, 36.9, -2.9, 37.0), "2022-06-01", "2022-08-31", "2022-10-01", "2022-11-30",
                        perimeter = "fire.gpkg", burned_min = 0.27, min_ha = 2)
  expect_equal(sent$perimeter, "fire.gpkg")
  expect_equal(sent$burned_min, 0.27)
  expect_equal(sent$min_ha, 2)
  expect_equal(attr(x, "perimeter"), "fire.gpkg")
  expect_equal(attr(x, "perimeter_ha"), c(fire = 4.5))
  expect_equal(attr(x, "perimeter_patches"), c(fire = 2L))
  expect_equal(attr(x, "burned_min"), 0.27)
  # without it, nothing about it
  answer[c("perimeter", "perimeter_ha", "perimeter_patches", "burned_min", "min_ha")] <- NULL
  y <- mo_burn_severity(mo_bbox(-3.0, 36.9, -2.9, 37.0), "2022-06-01", "2022-08-31", "2022-10-01", "2022-11-30")
  expect_null(sent$perimeter)
  expect_null(attr(y, "perimeter"))
})

test_that("the animation of a variable: its arguments reach the services, its frames come back", {
  sent <- NULL
  answer <- list(file = "ndvi.gif", gif = "ndvi.gif", n_frames = 2L, step = "annual",
                 frames = list(list(date = "2020-01-01", end = "2021-01-01", label = "2020", images = 12L),
                               list(date = "2021-01-01", end = "2022-01-01", label = "2021", images = 0L)),
                 references = list(), credits = list())
  local_mocked_bindings(services = function() list(timelapse = function(...) {
    sent <<- list(...)
    answer
  }), .package = "monitoreo")
  x <- mo_timelapse(mo_bbox(-3.45, 37.02, -3.30, 37.12), "NDVI", "Sentinel-2", "2020-01-01", "2021-12-31",
                    "ndvi.gif", step = "annual", fps = 3, dimensions = 400)
  expect_equal(sent$fps, 3)
  expect_identical(sent$dimensions, 400L)
  expect_equal(sent$path, "ndvi.gif")
  expect_equal(x$n_frames, 2L)
  expect_equal(x$frames[[2]]$images, 0L)
  expect_error(mo_timelapse(mo_bbox(-3.45, 37.02, -3.30, 37.12), "NDVI", start = "2020-01-01", end = "2021-12-31",
                            path = "ndvi.gif"), "sensor")
})

test_that("the area of each class: its arguments reach the services, a data.frame comes back", {
  sent <- NULL
  answer <- list(mode = "landcover", title = "Area of each class of CORINE Land Cover 2018", unit = "", scale = 100,
                 rows = list(list(region = "park", map = "CORINE Land Cover", year = 2018L, class = 311L,
                                  label = "311 Broad-leaved forest", landcover = "trees", ha = 120.5, percent = 60),
                             list(region = "park", map = "CORINE Land Cover", year = 2018L, class = 321L,
                                  label = "321 Natural grasslands", landcover = "grassland", ha = 80.3, percent = 40)),
                 by_landcover = list(list(region = "park", landcover = "trees", label = "Trees", ha = 120.5,
                                          percent = 60)),
                 references = list(), credits = list())
  local_mocked_bindings(services = function() list(area_by_class = function(...) {
    sent <<- list(...)
    answer
  }), .package = "monitoreo")
  x <- mo_area_by_class(mo_bbox(-3.45, 37.02, -3.30, 37.12), landcover = "CORINE", year = 2018)
  expect_identical(sent[[12]], 2018L)  # year
  expect_equal(nrow(x), 2)
  expect_equal(x$ha, c(120.5, 80.3))
  expect_equal(attr(x, "mode"), "landcover")
  expect_equal(nrow(attr(x, "by_landcover")), 1)
  mo_area_by_class(mo_bbox(-3.45, 37.02, -3.30, 37.12), "ELEVATION", "Copernicus", breaks = c(1500, 2000))
  expect_equal(sent[[13]], list(1500, 2000))  # breaks
  expect_error(mo_area_by_class(mo_bbox(-3.45, 37.02, -3.30, 37.12), "NDVI", trend = TRUE), "sensor")
})

test_that("the gradients: the zones of region_stats and the profile along a line reach the services", {
  sent <- NULL
  local_mocked_bindings(services = function() list(
    region_stats = function(...) {
      sent <<- list(...)
      list(rows = list(list(region = "park", zone = 0L, zone_label = "below 1500 m", p50 = 0.4, n_pixels = 10L)),
           title = "NDVI", unit = "", scale = 250, references = list(), credits = list())
    },
    transect = function(...) {
      sent <<- list(...)
      list(rows = list(list(distance_m = 500, value = 43.6, elevation = 684, lon = -3.59, lat = 37.15)),
           title = "LST", unit = "[°C]", length_m = 1000, spacing = 1000, references = list(), credits = list())
    }), .package = "monitoreo")
  x <- mo_region_stats(mo_bbox(-3.45, 37.02, -3.30, 37.12), "NDVI", "Modis", "2023-06-01", "2023-08-31",
                       zones = list(variable = "ELEVATION", sensor = "Copernicus", breaks = c(1500, 2000)))
  expect_equal(sent$zones$breaks, list(1500, 2000))
  expect_equal(x$zone_label, "below 1500 m")
  p <- mo_transect(rbind(c(-3.60, 37.15), c(-3.39, 37.06)), "LST", "Modis", "2023-07-01", "2023-08-31")
  expect_equal(sent[[1]], list(c(-3.60, 37.15), c(-3.39, 37.06)))
  expect_equal(p$elevation, 684)
  expect_equal(attr(p, "length_m"), 1000)
})

test_that("the figure of a map: its arguments reach the services", {
  sent <- NULL
  local_mocked_bindings(services = function() list(map_figure = function(...) {
    sent <<- list(...)
    list(file = "ndvi.pdf", min = 0.2, max = 0.7, references = list(), credits = list())
  }), .package = "monitoreo")
  x <- mo_map_figure(mo_bbox(-3.45, 37.02, -3.30, 37.12), "NDVI", "Modis", "2023-06-01", "2023-08-31", "ndvi.pdf",
                     dpi = 150)
  expect_equal(sent$path, "ndvi.pdf")
  expect_identical(sent$dpi, 150L)
  expect_equal(x$file, "ndvi.pdf")
})

test_that("the search of the Earth Engine data catalog, without Earth Engine", {
  skip_if_no_python()
  x <- mo_find_datasets("snow cover", limit = 3)
  expect_equal(x$id[1], "MODIS/061/MOD10A1")
  expect_true(all(c("title", "type", "start", "page") %in% names(x)))
  expect_type(x$keywords, "character")
  # the images (fixed layers) whatever the dates; the collections that go on, without end
  x <- mo_find_datasets("worldclim", start = "2020-01-01", end = "2021-12-31")
  expect_true("WORLDCLIM/V1/BIO" %in% x$id)
  x <- mo_find_datasets("sentinel-2 surface reflectance", limit = 5)  # all of them go on
  expect_true("end" %in% names(x) && is.na(x$end[x$id == "NASA/HLS/HLSS30/v002"]))
})

test_that("the time series by day of the year: doy reaches the services, mo_plot draws a line per year", {
  sent <- NULL
  rows <- list()
  for (g in c("park", "buffer")) for (y in 2023:2024) for (d in c(1, 182)) {
    date <- format(as.Date(sprintf("%d-01-01", y)) + d - 1)
    rows[[length(rows) + 1]] <- list(region = g, date = date, value = d / 100 + (y - 2023), n_pixels = 4L,
                                     n_images = 1L, year = y, doy = as.integer(format(as.Date(date), "%j")))
  }
  local_mocked_bindings(services = function() list(time_series = function(...) {
    sent <<- list(...)
    list(rows = rows, title = "16-day NDSI (MODIS), mean | by day of the year", unit = "1", ylabel = "NDSI",
         scale = 500, references = list(), credits = list())
  }), .package = "monitoreo")
  ts <- mo_time_series(mo_bbox(-3.45, 37.02, -3.30, 37.12), "NDSI", "Modis", "2023-01-01", "2024-12-31",
                       step = "16-day", doy = TRUE)
  expect_true(sent$doy)
  expect_equal(ts$doy[1:2], c(1, 182))
  skip_if_not_installed("ggplot2")
  p <- mo_plot(ts)
  expect_s3_class(p, "ggplot")
  expect_equal(rlang::as_label(p$mapping$x), "doy")  # over the days of the year, not over the dates
  expect_equal(rlang::as_label(p$mapping$colour), "year")
  expect_s3_class(p$facet, "FacetWrap")  # a panel per region
  expect_equal(rlang::as_label(mo_plot(ts[ts$region == "park", ])$mapping$x), "doy")
  # with base graphics (without ggplot2): a line per year too
  base <- mo_plot
  environment(base) <- list2env(list(requireNamespace = function(...) FALSE), parent = environment(mo_plot))
  grDevices::pdf(NULL)
  on.exit(grDevices::dev.off(), add = TRUE)
  expect_identical(base(ts), ts)
})

test_that("the seasonal profile by day of the year: its options reach the services, mo_plot draws two y axes", {
  sent <- NULL
  vars <- c("NDVI Landsat", "SCF Landsat")
  starts <- c(1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)
  profile <- list()
  for (g in c("buffer", "park")) for (v in vars) for (m in 1:12) {
    winter <- cos(2 * pi * (m - 1) / 12)
    value <- if (m == 12) NULL else if (v == vars[1]) 0.3 - winter / 4 else max(0, 80 * winter)
    profile[[length(profile) + 1]] <- list(region = g, variable = v, part = as.character(m), doy = starts[m],
                                           label = month.abb[m], value = value, n_years = if (m == 12) 0L else 3L)
  }
  yearly <- lapply(vars, function(v) list(region = "buffer", date = "2021-01-01", value = 0.05, n_pixels = 5L,
                                          n_images = 1L, year = 2021L, doy = 1L, variable = v))
  # what Python returns (its tuples and dictionaries as lists): the NDVI in the range given (-1 to 1), the SCF (in %)
  # from the data
  answer <- list(rows = yearly, profile = profile, variables = as.list(vars),
                 units = stats::setNames(list("[unitless]", "[%]"), vars), scales = stats::setNames(list(30, 30), vars),
                 interannual = "p25", unit = "[unitless]", ylabel = "[unitless]",
                 other_ylabel = "Snow Cover Frequency (SCF) [%]", ylim = list(-1, 1), other_ylim = NULL,
                 title = paste("NDVI Landsat and SCF Landsat | 2021-01-01 / 2023-12-31 | monthly mean, spatial mean |",
                               "p25 of the years by day of the year"), scale = 30, csv = "profile.csv",
                 references = list(list(text = "Tucker, C. J. (1979). Red and photographic infrared.")),
                 credits = list("Landsat imagery courtesy of the U.S. Geological Survey"))
  local_mocked_bindings(services = function() list(time_series = function(...) {
    sent <<- list(...)
    answer
  }), .package = "monitoreo")
  region <- mo_bbox(-3.45, 37.02, -3.30, 37.12)
  p <- mo_time_series(region, "NDVI", "Landsat", "2021-01-01", "2023-12-31", doy = TRUE, interannual = "p25",
                      other_variable = "SCF", ylim = c(-1, 1))
  expect_true(sent$doy)
  expect_equal(sent[c("interannual", "other_variable", "ylim")],
               list(interannual = "p25", other_variable = "SCF", ylim = list(-1, 1)))  # two numbers, a list
  expect_true(all(c("other_sensor", "other_ylim") %in% names(sent)))  # sent by name, NULL: those of Python
  expect_null(sent$other_sensor)
  expect_null(sent$other_ylim)
  # the profile is the data.frame, the values of each year an attribute
  expect_equal(names(p), c("region", "variable", "part", "doy", "label", "value", "n_years"))
  expect_equal(nrow(p), 48)
  expect_equal(p$part[1:12], as.character(1:12))
  expect_equal(p$label[1:12], month.abb)
  expect_true(is.na(p$value[12]) && p$n_years[12] == 0)  # a step without a value in any year, kept
  expect_equal(attr(p, "variables"), vars)
  expect_equal(attr(p, "units"), c("NDVI Landsat" = "[unitless]", "SCF Landsat" = "[%]"))
  expect_equal(attr(p, "scales"), c("NDVI Landsat" = 30, "SCF Landsat" = 30))
  expect_equal(attr(p, "interannual"), "p25")
  expect_equal(attr(p, "ylim"), c(-1, 1))
  expect_null(attr(p, "other_ylim"))  # from the data
  expect_equal(attr(p, "other_ylabel"), "Snow Cover Frequency (SCF) [%]")
  expect_equal(attr(p, "csv"), "profile.csv")
  expect_equal(attr(p, "rows")$variable, vars)
  expect_s3_class(attr(p, "rows")$date, "Date")
  expect_match(capture.output(mo_references(p))[1], "^Tucker")
  # a line per year with a range of the y axis: sent as two numbers, kept for mo_plot
  answer <- list(rows = lapply(2021:2022, function(y) list(region = "park", date = sprintf("%d-07-01", y),
                                                            value = 0.4, n_pixels = 5L, n_images = 1L, year = y,
                                                            doy = 182L)),
                 title = "Monthly NDVI (Landsat), mean | by day of the year", unit = "[unitless]",
                 ylabel = "[unitless]", ylim = list(0, 1), scale = 30, references = list(), credits = list())
  ts <- mo_time_series(region, "NDVI", "Landsat", "2021-01-01", "2022-12-31", doy = TRUE, ylim = c(0, 1))
  expect_equal(sent$ylim, list(0, 1))
  expect_null(sent$interannual)
  expect_equal(names(ts), c("region", "date", "value", "n_pixels", "n_images", "year", "doy"))
  expect_equal(attr(ts, "ylim"), c(0, 1))
  expect_null(attr(ts, "variables"))
  # a range that is not two numbers, or data of Earth Engine on the right axis: an error of R, before Python
  sent <- NULL
  expect_error(mo_time_series(region, "NDVI", "Landsat", "2021-01-01", "2022-12-31", doy = TRUE, ylim = 1),
               "ylim: give two numbers, the lowest and the highest value of the y axis, e.g. c(-1, 1)", fixed = TRUE)
  expect_error(mo_time_series(region, "NDVI", "Landsat", "2021-01-01", "2022-12-31", doy = TRUE,
                              other_variable = "SCF", other_ylim = c("0", "100")), "^other_ylim: give two numbers")
  expect_error(mo_time_series(region, "NDVI", "Landsat", "2021-01-01", "2022-12-31", doy = TRUE,
                              other_ylim = c(0, NA)), "^other_ylim: give two numbers")
  expect_error(mo_time_series(region, "NDVI", "Landsat", "2021-01-01", "2022-12-31", doy = TRUE,
                              other_variable = "MODIS/061/MOD13Q1"),
               paste("other_variable MODIS/061/MOD13Q1: the variable of the right axis is a variable of the catalog",
                     "of MonitorEO (e.g. NDVI, see mo_variables()), not data of Earth Engine by its ID"), fixed = TRUE)
  expect_null(sent)
  skip_if_not_installed("ggplot2")
  g <- mo_plot(p)
  expect_s3_class(g, "ggplot")
  expect_equal(rlang::as_label(g$mapping$x), "doy")  # over the days of the year
  expect_equal(rlang::as_label(g$mapping$colour), "variable")  # a line per variable
  expect_equal(g$coordinates$limits$y, c(-1, 1))  # the left axis: the NDVI from -1 to 1
  # the right axis, the SCF from the data (0 to 80) with a margin of 5 %: its values drawn with the linear transform
  # from its range to that of the left axis, and its axis (sec_axis) back
  scf <- g$data[g$data$variable == vars[2], ]
  expect_equal(scf$plotted, -1 + (scf$value + 4) * 2 / 88)
  y <- g$scales$get_scales("y")
  expect_s3_class(y$secondary.axis, "AxisSecondary")
  expect_equal(y$secondary.axis$trans(c(-1, 0, 1)), c(-4, 40, 84))
  expect_equal(y$secondary.axis$name, "Snow Cover Frequency (SCF) [%]")
  expect_equal(y$name, "[unitless]")
  expect_equal(unname(g$scales$get_scales("colour")$palette(2)), c("#1f77b4", "#d62728"))  # left, right
  # a line at 0 of each axis: that of the right one, dotted, where its 0 is on the left one
  zeros <- Filter(function(l) inherits(l$geom, "GeomHline"), g$layers)
  expect_equal(unname(vapply(zeros, function(l) l$data$yintercept, 0)), c(0, -1 + 4 * 2 / 88))
  expect_s3_class(g$facet, "FacetWrap")  # a panel per region
  # the rows of one variable: one axis, with its own range and title, in the colour of its line
  right <- mo_plot(p[p$variable == vars[2], ])
  expect_equal(right$coordinates$limits$y, c(-4, 84))
  expect_false(inherits(right$scales$get_scales("y")$secondary.axis, "AxisSecondary"))
  expect_equal(right$scales$get_scales("y")$name, "Snow Cover Frequency (SCF) [%]")
  expect_equal(unname(right$scales$get_scales("colour")$palette(1)), "#d62728")
  # without the attributes (subset()): the variables of the rows, their names as titles, the ranges from the data
  bare <- mo_plot(subset(p, region == "park"))
  expect_equal(bare$scales$get_scales("y")$secondary.axis$name, vars[2])
  expect_equal(bare$coordinates$limits$y, c(0.05, 0.55) + c(-1, 1) * 0.025)
  # a line per year in the range that was given
  expect_equal(mo_plot(ts)$coordinates$limits$y, c(0, 1))
  # with base graphics (without ggplot2): the right axis drawn last, on its own scale
  base <- mo_plot
  environment(base) <- list2env(list(requireNamespace = function(...) FALSE), parent = environment(mo_plot))
  grDevices::pdf(NULL)
  on.exit(grDevices::dev.off(), add = TRUE)
  expect_identical(base(p), p)
  expect_equal(graphics::par("usr"), c(1, 366, -4, 84))
  expect_identical(base(p[p$variable == vars[1], ]), p[p$variable == vars[1], ])
  expect_equal(graphics::par("usr"), c(1, 366, -1, 1))
  expect_identical(base(ts), ts)
  expect_equal(graphics::par("usr")[3:4], c(0, 1))
})

test_that("the seasonal profile of two indices from Python, without Earth Engine: each axis from its values", {
  skip_if_no_python()
  # the series of each variable from a fake timeseries.series (the NDSI in winter, the NDVI in summer, nothing in
  # February 2022), and the region not computed, as in tests/test_doy_profile.py; restored at the end
  reticulate::py_run_string(paste(sep = "\n",
    "import datetime as _mo_dt, math as _mo_math",
    "from monitoreo import services as _mo_services, timeseries as _mo_timeseries",
    "_mo_saved = (_mo_services.areas.region, _mo_timeseries.series)",
    "def _mo_series(spec, regions, step='monthly', metric='mean', stat='mean', scale=None, progress=None, steps=None):",
    "    rows = []",
    "    for a, _ in _mo_timeseries.bins(spec, step):",
    "        d = _mo_dt.date.fromisoformat(a)",
    "        winter = _mo_math.cos(2 * _mo_math.pi * (d.month - 1) / 12)",
    "        v = {'NDSI': winter / 2, 'NDVI': 0.3 - winter / 4}[spec['index']] + (d.year - 2021) / 100",
    "        rows += [{'region': g, 'date': a, 'value': None if a.startswith('2022-02') else v, 'n_pixels': 5,",
    "                  'n_images': 1} for g in ('park', 'buffer')]",
    "    return sorted(rows, key=lambda r: (r['region'], r['date'])), scale or 10.0",
    "def _mo_fail(region):",
    "    raise RuntimeError('computed before checking the call')",
    "def _mo_restore():",
    "    _mo_services.areas.region, _mo_timeseries.series = _mo_saved",
    "_mo_services.areas.region = lambda region: 'regions'",
    "_mo_timeseries.series = _mo_series"))
  on.exit(reticulate::py_run_string("_mo_restore()"), add = TRUE)
  csv <- tempfile(fileext = ".csv")
  p <- mo_time_series(mo_bbox(-3.62, 36.86, -3.50, 36.93), "NDSI", "Sentinel-2", "2021-01-01", "2023-12-31",
                      doy = TRUE, other_variable = "NDVI", csv = csv)
  vars <- c("NDSI Sentinel-2", "NDVI Sentinel-2")
  expect_equal(names(p), c("region", "variable", "part", "doy", "label", "value", "n_years"))
  expect_equal(nrow(p), 48)  # 12 months, 2 variables, 2 regions
  expect_equal(unique(p$variable), vars)
  expect_equal(p$part[1:12], as.character(1:12))
  expect_equal(p$label[1:12], month.abb)
  expect_equal(p$value[1], 0.51)  # the median of the January of 2021, 2022 and 2023: 0.50, 0.51 and 0.52
  expect_equal(p$n_years[1:2], c(3, 2))  # February of 2022 without a value
  expect_equal(attr(p, "variables"), vars)
  expect_equal(attr(p, "interannual"), "median")  # by default with other_variable
  expect_null(attr(p, "ylim"))  # none given: each axis from the values of its own variable
  expect_null(attr(p, "other_ylim"))
  expect_equal(attr(p, "units"), c("NDSI Sentinel-2" = "[unitless]", "NDVI Sentinel-2" = "[unitless]"))
  expect_equal(attr(p, "scales"), c("NDSI Sentinel-2" = 10, "NDVI Sentinel-2" = 10))
  expect_match(attr(p, "title"), "^NDSI Sentinel-2 and NDVI Sentinel-2 \\| .*\\| median of the years by day of the year$")
  rows <- attr(p, "rows")
  expect_equal(nrow(rows), 144)  # 36 months, 2 variables, 2 regions
  expect_equal(unique(rows$variable), vars)
  expect_true(all(c("year", "doy") %in% names(rows)))
  expect_s3_class(rows$date, "Date")
  table <- utils::read.csv(csv)  # the profile, what the chart shows
  expect_equal(names(table), c("region", "variable", "part", "doy", "label", "value", "n_years", "sensor", "step",
                               "metric", "stat", "interannual", "unit", "scale_m"))
  expect_equal(nrow(table), 48)
  expect_true(file.exists(attr(p, "readme")))
  refs <- attr(p, "references")
  expect_true(any(grepl("^Hall, D. K., Riggs, G. A., & Salomonson", refs)))  # the NDSI
  expect_true(any(grepl("^Tucker, C. J. \\(1979\\)", refs)))  # and the NDVI, the other variable
  # the errors of Python come before Earth Engine (the region is not even computed), in the words of the call
  reticulate::py_run_string("_mo_services.areas.region = _mo_fail")
  run <- function(...) mo_time_series(mo_bbox(-3.62, 36.86, -3.50, 36.93), "NDSI", "Sentinel-2", "2021-01-01",
                                      "2022-12-31", ...)
  expect_error(run(interannual = "median"), "interannual: only for the chart by day of the year (doy)", fixed = TRUE)
  expect_error(run(ylim = c(-1, 1), other_ylim = c(0, 1)), "ylim, other_ylim: only for the chart by day of the year",
               fixed = TRUE)
  expect_error(run(doy = TRUE, step = "annual", other_variable = "NDVI"), "needs a step shorter than a year")
  expect_error(run(doy = TRUE, interannual = "sum"), "unknown metric between the years (interannual) sum",
               fixed = TRUE)
  expect_error(run(doy = TRUE, other_sensor = "Modis"), "give other_variable")
  expect_error(run(doy = TRUE, metric = "median", other_variable = "SCF", other_sensor = "Landsat"),
               "other_variable (the right axis): SCF (Landsat) only takes the metric 'mean'", fixed = TRUE)
  expect_error(run(doy = TRUE, other_variable = "ELEVATION", other_sensor = "Copernicus"),
               "is a fixed layer, without dates")
  expect_error(run(doy = TRUE, other_variable = "NDSI"), "NDSI Sentinel-2 is already the variable of the left axis")
  expect_error(run(doy = TRUE, interannual = "median", ylim = c(1, 0)),
               "ylim: the first number of the y axis (1) must be smaller than the second (0)", fixed = TRUE)
  skip_if_not_installed("ggplot2")
  g <- mo_plot(p)
  # each axis from the minimum to the maximum of its own variable, with a margin of 5 %: the NDSI on the left, the
  # NDVI on the right (the secondary axis: the linear transform from the range of the left axis to its own)
  own <- function(v) {
    r <- range(p$value[p$variable == v], na.rm = TRUE)
    r + c(-1, 1) * 0.05 * diff(r)
  }
  expect_equal(g$coordinates$limits$y, own(vars[1]))
  expect_equal(g$scales$get_scales("y")$secondary.axis$trans(own(vars[1])), own(vars[2]))
  expect_false(isTRUE(all.equal(own(vars[1]), own(vars[2]))))
  expect_false(isTRUE(all.equal(own(vars[1]), c(-1, 1))))
})

test_that("burn severity with the RdNBR: its legend, sensors and errors, without Earth Engine", {
  skip_if_no_python()
  # the classes of Miller & Thode 2007 (Table 4, / 1000) with the colours of their maps in the other tools
  leg <- monitoreo:::burn_legend("RdNBR")
  expect_equal(leg$value, 0:3)
  expect_equal(leg$label, c("Unchanged", "Low severity", "Moderate severity", "High severity"))
  expect_equal(leg$color, c("#0ae042", "#fff70b", "#ff641b", "#a41fd6"))
  expect_equal(leg$rdnbr_min, c(NA, 0.069, 0.316, 0.641))
  expect_equal(leg$rdnbr_max, c(0.069, 0.316, 0.641, NA))
  expect_true("dnbr_min" %in% names(monitoreo:::burn_legend("dNBR")))
  # its variables: Sentinel-2, Landsat and MODIS (Terra and Aqua), only for mo_burn_severity
  v <- mo_variables(text = "RdNBR")
  expect_setequal(unique(v$sensor), c("Sentinel-2", "Landsat", "Modis"))
  expect_setequal(v$collection[v$sensor == "Modis"], c("MODIS/061/MOD09GA", "MODIS/061/MYD09GA"))
  expect_true(all(v$two_periods))
  region <- mo_bbox(-3.0, 36.9, -2.9, 37.0)
  expect_error(mo_time_series(region, "RdNBR", "Modis", "2022-06-01", "2022-08-31"),
               "compute it with burn_severity and index 'RdNBR'", fixed = TRUE)
  # refused before Earth Engine: MODIS and collection only for the RdNBR, and an unknown index
  expect_error(mo_burn_severity(region, "2022-06-01", "2022-08-31", "2023-06-01", "2023-08-31", sensor = "Modis"),
               "MODIS only with index RdNBR")
  expect_error(mo_burn_severity(region, "2022-06-01", "2022-08-31", "2023-06-01", "2023-08-31", index = "RBR",
                                collection = "MODIS/061/MYD09GA"), "collection is only for the index RdNBR")
  expect_error(mo_burn_severity(region, "2022-06-01", "2022-08-31", "2023-06-01", "2023-08-31", index = "dNDVI"),
               "unknown burn index: use dNBR, RBR or RdNBR")
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

test_that("data of Earth Engine by its ID with Earth Engine", {
  skip_if_no_python()
  skip_if(Sys.getenv("EE_PROJECT") == "", "EE_PROJECT not set")
  mo_init()
  region <- mo_bbox(-3.62, 36.86, -3.50, 36.93)
  # a collection of images with dates, of the Earth Engine data catalog
  a <- mo_asset("IDAHO_EPSCOR/TERRACLIMATE")
  expect_equal(a$type, "image_collection")
  expect_equal(a$use, "collection")
  expect_equal(a$source, "Earth Engine data catalog")
  expect_true("pr" %in% vapply(a$bands, function(b) b$band, ""))
  expect_equal(a$arguments$collection, "IDAHO_EPSCOR/TERRACLIMATE")
  expect_true(any(grepl("10.1038/sdata.2017.191", capture.output(mo_references(a)), fixed = TRUE)))
  ts <- mo_time_series(region, collection = "IDAHO_EPSCOR/TERRACLIMATE", band = "pr", unit = "mm",
                       start = "2021-01-01", end = "2021-06-30")
  expect_equal(nrow(ts), 6)
  expect_true(all(ts$value >= 0))
  expect_equal(attr(ts, "unit"), "mm")
  expect_match(attr(ts, "title"), "IDAHO_EPSCOR/TERRACLIMATE pr", fixed = TRUE)
  expect_true(any(grepl("^Abatzoglou", attr(ts, "references"))))
  # a fixed image: maps and their statistics
  expect_equal(mo_asset("WORLDCLIM/V1/BIO")$use, "image")
  st <- mo_region_stats(region, image = "WORLDCLIM/V1/BIO", band = "bio01", band_scale = 0.1, unit = "degC")
  expect_true(st$mean > 5 && st$mean < 25)  # the annual mean temperature, in degrees Celsius
  expect_equal(attr(st, "unit"), "degC")
  expect_equal(attr(st, "title"), "WORLDCLIM/V1/BIO bio01")
  img <- mo_image(region, image = "WORLDCLIM/V1/BIO", band = "bio01", band_scale = 0.1, unit = "degC")
  expect_true(inherits(img$image, "ee.image.Image"))
  expect_equal(img$name, "WORLDCLIM/V1/BIO bio01")
  expect_true(img$vis$min < img$vis$max)
  expect_true(length(img$references) > 0)
  m <- mo_map_layer(region, image = "WORLDCLIM/V1/BIO", band = "bio01", band_scale = 0.1, unit = "degC")
  expect_match(m$url, "^https://.*\\{z\\}")
  expect_equal(m$unit, "degC")
  # an image given as a collection
  expect_error(mo_time_series(region, collection = "WORLDCLIM/V1/BIO", band = "bio01", start = "2021-01-01",
                              end = "2021-06-30"), "give it as image=")
})
