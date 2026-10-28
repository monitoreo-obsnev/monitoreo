# MonitorEO (OBSNEV) for R: the functions of the Python package monitoreo (monitoreo.services) through reticulate,
# so R computes exactly the same as the QGIS plugin and the MCP server. With rgee, the images of mo_image() are
# Earth Engine objects that rgee::Map$addLayer() shows.

.mo <- new.env(parent = emptyenv())
utils::globalVariables(c("date", "value", "region"))

services <- function() {
  if (is.null(.mo$services)) {
    if (!reticulate::py_module_available("monitoreo")) {
      stop("the Python package monitoreo is not in the Python of reticulate (", reticulate::py_config()$python,
           "): install it with mo_install(), or choose a Python that has it with reticulate::use_python() or the ",
           "variable RETICULATE_PYTHON before mo_init()", call. = FALSE)
    }
    .mo$services <- reticulate::import("monitoreo.services", convert = TRUE)
  }
  .mo$services
}

#' Install the Python package monitoreo in the Python of reticulate (that of rgee, if rgee is used).
#' @param source pip source: a GitHub URL ("git+https://github.com/monitoreo-obsnev/monitoreo") or a local folder.
#' @export
mo_install <- function(source = "git+https://github.com/monitoreo-obsnev/monitoreo", ...) {
  reticulate::py_install(source, pip = TRUE, ...)
  invisible(TRUE)
}

#' Connect to Earth Engine with the credentials of `earthengine authenticate` (or rgee::ee_Initialize()) and a
#' Google Cloud project registered in Earth Engine.
#' @param project project (default: the variable EE_PROJECT).
#' @param python optional path of the Python with monitoreo (see reticulate::use_python()).
#' @export
mo_init <- function(project = Sys.getenv("EE_PROJECT"), python = NULL) {
  if (!is.null(python)) reticulate::use_python(python, required = TRUE)
  if (!nzchar(project)) project <- NULL
  invisible(services()$init(project))
}

# A list of Python dictionaries (rows) as a data.frame, with dates as Date and None as NA.
rows_df <- function(rows) {
  if (length(rows) == 0) return(data.frame())
  cols <- unique(unlist(lapply(rows, names)))
  df <- as.data.frame(lapply(stats::setNames(cols, cols), function(col) {
    v <- lapply(rows, function(r) if (is.null(r[[col]])) NA else r[[col]])
    unlist(v)
  }), stringsAsFactors = FALSE)
  if ("date" %in% names(df)) df$date <- as.Date(df$date)
  df
}

#' Variables of the catalog of MonitorEO.
#' @export
mo_variables <- function(sensor = NULL, text = NULL, lang = "es") {
  rows_df(services()$list_variables(sensor, text, lang))
}

#' Everything about a variable of the catalog (formula, collection, unit, pixel filters, notes...).
#' @export
mo_describe <- function(variable, sensor = NULL, collection = NULL) {
  services()$describe_variable(variable, sensor, collection)
}

#' Protected areas of WDPA whose name contains `text` (SITE_ID is the WDPA ID).
#' @export
mo_protected_areas <- function(text, limit = 20) {
  rows_df(services()$find_protected_areas(text, as.integer(limit)))
}

#' Regions: protected areas by WDPA ID, ecoregions of RESOLVE 2017, a box, a point or GeoJSON / sf objects.
#' @export
mo_wdpa <- function(id) list(wdpa_id = as.list(as.integer(id)))
#' @export
mo_ecoregion <- function(id = NULL, lon = NULL, lat = NULL) {
  if (!is.null(id)) list(ecoregion_id = as.list(as.integer(id))) else list(ecoregion_at = list(lon, lat))
}
#' @export
mo_bbox <- function(west, south, east, north) list(bbox = list(west, south, east, north))
#' @export
mo_point <- function(lon, lat, buffer = 0) list(point = list(lon, lat), buffer = buffer)
#' @export
mo_geojson <- function(geojson, name_field = NULL) {
  if (!is.character(geojson)) geojson <- jsonlite::toJSON(geojson, auto_unbox = TRUE, digits = NA)
  list(geojson = as.character(geojson), name_field = name_field)
}

#' A region from an sf object (polygons, any CRS); `name` is the column with the names of its features.
#' @export
mo_sf <- function(x, name = NULL) {
  x <- sf::st_transform(sf::st_zm(x), 4326)
  x$name <- if (is.null(name)) as.character(seq_len(nrow(x))) else as.character(x[[name]])
  path <- tempfile(fileext = ".geojson")
  sf::st_write(x["name"], path, quiet = TRUE)
  on.exit(unlink(path))
  mo_geojson(paste(readLines(path, warn = FALSE), collapse = "\n"))
}

#' Time series of a variable over a region: a value per step ("daily", "16-day", "monthly", "annual") and feature
#' of the region, reduced in time with `metric` and over the region with `stat`, with the number of images and of
#' valid pixels of each value. Returns a data.frame (region, date, value, n_pixels, n_images) with the attributes
#' title, unit and scale.
#' @export
mo_time_series <- function(region, variable, sensor, start, end, step = "monthly", metric = "mean", stat = "mean",
                           season = NULL, quality = NULL, scale = NULL, csv = NULL, collection = NULL) {
  res <- services()$time_series(region, variable, sensor, start, end, step, metric, stat, season = season,
                                quality = quality, scale = scale, csv = csv, collection = collection)
  df <- rows_df(res$rows)
  attr(df, "title") <- res$title
  attr(df, "unit") <- res$unit
  attr(df, "scale") <- res$scale
  attr(df, "csv") <- res$csv
  df
}

#' Chart of a time series of mo_time_series() (ggplot2 if installed, else base graphics).
#' @export
mo_plot <- function(ts) {
  title <- attr(ts, "title")
  unit <- attr(ts, "unit")
  if (requireNamespace("ggplot2", quietly = TRUE)) {
    return(ggplot2::ggplot(ts, ggplot2::aes(x = date, y = value, colour = region)) +
      ggplot2::geom_line() + ggplot2::geom_point(size = 1) +
      ggplot2::labs(title = title, x = NULL, y = unit, colour = NULL) + ggplot2::theme_minimal())
  }
  regions <- unique(ts$region)
  plot(ts$date, ts$value, type = "n", main = title, xlab = "", ylab = unit)
  for (i in seq_along(regions)) {
    s <- ts[ts$region == regions[i], ]
    lines(s$date, s$value, col = i, type = "o", pch = 20)
  }
  if (length(regions) > 1) legend("topleft", legend = regions, col = seq_along(regions), lty = 1, bty = "n")
  invisible(ts)
}

#' Map of a variable over a region aggregated in time: URL of its Earth Engine map tiles (XYZ, valid for some
#' hours) and colour ramp. `thumbnail`: path of a PNG preview.
#' @export
mo_map_layer <- function(region, variable, sensor, start, end, metric = "median", temporal = "period",
                         interannual = "mean", season = NULL, quality = NULL, vmin = NULL, vmax = NULL,
                         thumbnail = NULL, collection = NULL) {
  services()$map_layer(region, variable, sensor, start, end, metric, temporal, interannual, season, quality, vmin,
                       vmax, thumbnail = thumbnail, collection = collection)
}

#' A leaflet map with the tiles of mo_map_layer().
#' @export
mo_leaflet <- function(layer) {
  leaflet::addTiles(leaflet::addProviderTiles(leaflet::leaflet(), "Esri.WorldImagery"), urlTemplate = layer$url,
                    attribution = "Google Earth Engine, MonitorEO", group = layer$name)
}

#' Earth Engine image (band "value") of a variable over a region aggregated in time, with its colour ramp: for
#' rgee, e.g. rgee::Map$addLayer(x$image, x$vis, x$name).
#' @export
mo_image <- function(region, variable, sensor, start, end, metric = "median", temporal = "period",
                     interannual = "mean", season = NULL, quality = NULL, clip = TRUE, collection = NULL) {
  s <- services()
  out <- s$composite_image(region, variable, sensor, start, end, metric, temporal, interannual, season, quality,
                           clip, collection = collection)
  maps <- reticulate::import("monitoreo.maps", convert = TRUE)
  catalog <- reticulate::import("monitoreo.catalog", convert = TRUE)
  entry <- tryCatch(catalog$find(variable, sensor, collection), error = function(e) NULL)
  vis <- maps$vis_params(out[[1]], out[[2]]$geometry(), entry, NULL)
  list(image = out[[1]], region = out[[2]], vis = vis, name = paste(variable, sensor, metric, start, end))
}

#' Statistics over each feature of a region of the map of a variable aggregated in time.
#' @export
mo_region_stats <- function(region, variable, sensor, start, end, metric = "median", temporal = "period",
                            season = NULL, quality = NULL, scale = NULL, collection = NULL) {
  res <- services()$region_stats(region, variable, sensor, start, end, metric, temporal, season = season,
                                 quality = quality, scale = scale, collection = collection)
  df <- rows_df(res$rows)
  attr(df, "title") <- res$title
  attr(df, "unit") <- res$unit
  attr(df, "scale") <- res$scale
  df
}

#' Export the map of a variable over a region to a GeoTIFF in a folder of Google Drive (see mo_task_status()).
#' @export
mo_export_image <- function(region, variable, sensor, start, end, metric = "median", temporal = "period",
                            season = NULL, quality = NULL, resolution = NULL, crs = "auto", folder = "MonitorEO",
                            name = NULL, collection = NULL) {
  services()$export_image(region, variable, sensor, start, end, metric, temporal, season = season,
                          quality = quality, resolution = resolution, crs = crs, folder = folder, name = name,
                          collection = collection)
}

#' Export a time series to a CSV file in a folder of Google Drive (see mo_task_status()).
#' @export
mo_export_time_series <- function(region, variable, sensor, start, end, step = "monthly", metric = "mean",
                                  stat = "mean", season = NULL, quality = NULL, scale = NULL, folder = "MonitorEO",
                                  name = NULL, collection = NULL) {
  services()$time_series_to_drive(region, variable, sensor, start, end, step, metric, stat, season, quality, scale,
                                  folder, name, collection = collection)
}

#' State of an export task: PENDING, RUNNING, SUCCEEDED, FAILED or CANCELLED.
#' @export
mo_task_status <- function(operation) services()$task_status(operation)
