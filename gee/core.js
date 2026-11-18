/*
 * MonitorEO in JavaScript: the core of the Python package monitoreo (src/monitoreo) ported to the Earth Engine
 * JavaScript API, for the app of the Code Editor (ui.js) and for the tests that compare both (tests/test_gee.py).
 *
 * It uses the globals ee and CATALOG (catalog.js, written by build.py from catalog.json with the formulas already
 * resolved to band names). ES5 only, as the Code Editor. Every function keeps the name and the behaviour of the
 * Python function it ports (module.function in the comments): change both together.
 *
 * A spec names a variable of the catalog by its ref, or carries the entry of the data of Earth Engine outside the
 * catalog that it computes (spec.entry, see customEntry): any image or collection of images given by its ID.
 */

var MonitorEO = (function () {

	// Catalog (catalog.py) ------------------------------------------------------------------------------------------

	function variables() {
		return CATALOG.variables;
	}

	function byRef(ref) {
		var entries = variables();
		for (var i = 0; i < entries.length; i++) {
			if (entries[i].ref === Number(ref)) return entries[i];
		}
		throw new Error('no entry with ref ' + ref + ' in the catalog of MonitorEO');
	}

	// catalog.name_key: NAME (of a variable or a sensor) as the catalog compares it, in lower case and without spaces
	function nameKey(name) {
		return String(name).toLowerCase().replace(/ /g, '');
	}

	// catalog.find: the entry of a variable by REF, or by INDEX and SENSOR and, when several collections have them
	// (MOD13Q1 and MYD13Q1), COLLECTION (without it, the first entry); an Error with the options if there is none
	function findEntry(index, sensor, collection, ref) {
		if (ref !== null && ref !== undefined) return byRef(ref);
		var none = function (x) { return x === null || x === undefined; };
		var matches = variables().filter(function (e) {
			return nameKey(e.index) === nameKey(index) && (none(sensor) || nameKey(e.sensor) === nameKey(sensor)) &&
				(none(collection) || e.col === collection);
		});
		if (!matches.length) {
			var options = [];
			variables().forEach(function (e) {
				var o = e.index + ' (' + e.sensor + ')';
				if ((nameKey(e.index) === nameKey(index) || none(sensor)) && options.indexOf(o) < 0) options.push(o);
			});
			throw new Error((none(index) ? 'None' : index) + ' with sensor ' + (none(sensor) ? 'None' : sensor) +
				(collection ? ' and collection ' + collection : '') + ' is not in the catalog of MonitorEO. Options: ' +
				(options.sort().join(', ') || 'see the list of variables (list_variables)'));
		}
		return matches[0];
	}

	// catalog.number: number of a field of the catalog ('#' or missing = DEFAULT)
	function number(v, def) {
		var x = parseFloat(v);
		return isNaN(x) ? def : x;
	}

	// Dates (client side, in UTC) -----------------------------------------------------------------------------------

	function date(text) {
		var p = String(text).split('-');
		return new Date(Date.UTC(Number(p[0]), Number(p[1]) - 1, Number(p[2])));
	}

	function ymd(y, m, d) {
		return new Date(Date.UTC(y, m - 1, d));
	}

	function iso(d) {
		return d.toISOString().slice(0, 10);
	}

	function addDays(d, n) {
		return new Date(d.getTime() + n * 86400000);
	}

	function daysInMonth(y, m) {
		return new Date(Date.UTC(y, m, 0)).getUTCDate();
	}

	function minDate(a, b) {
		return a < b ? a : b;
	}

	function maxDate(a, b) {
		return a > b ? a : b;
	}

	// Temporal aggregation (composite.py) ---------------------------------------------------------------------------

	var TEMPORAL = ['period', 'annual', 'monthly', '16-day'];
	var METRICS = 'mean, median, mode, min, max, sum, std (standard deviation), cv (coefficient of variation, %), ' +
		'count or pN (percentile N, e.g. p95, p2.5)';
	var SIMPLE = ['mean', 'median', 'mode', 'min', 'max', 'sum', 'std', 'cv', 'count'];
	var DAYS = 'days';  // composite.DAYS: the snow cover days, the only metric of the variable SCD (see days)
	// composite.CV: the coefficient of variation, 100 × the standard deviation / the mean, in % (Pearson 1896), of the
	// images of each pixel or of the pixels of a region, computed from the reducers of the mean and of the standard
	// deviation (population), without a value where the mean is 0; composite.SPREAD: the metrics whose values are not in
	// the range of the variable (their colour ramp comes from the map, see rampEntry)
	var CV = 'cv';
	var SPREAD = ['std', 'cv'];
	// composite.RGB_METRICS: the metrics of the true colour (RGB) of the images of a variable: each band with the
	// metric (mean, median or pN), or, with max and min, the bands of the image where the variable is highest or lowest
	// on each pixel (composite.MOSAICS: Earth Engine qualityMosaic), so that the colours are those of one date
	var RGB_METRICS = 'mean, median, min, max or pN';
	var MOSAICS = ['max', 'min'];

	// composite.is_cv
	function isCv(metric) {
		return String(metric || '').trim().toLowerCase() === CV;
	}

	// composite.is_days
	function isDays(metric) {
		return typeof metric === 'string' && metric.trim().toLowerCase() === DAYS;
	}

	// composite.reducer (that of the coefficient of variation: of the mean and the standard deviation, outputs mean and
	// stdDev, from which cv and cvValue compute it)
	function reducer(metric) {
		var m = String(metric).trim().toLowerCase();
		var simple = {mean: 'mean', median: 'median', mode: 'mode', min: 'min', max: 'max', sum: 'sum', std: 'stdDev',
			count: 'count'};
		if (simple[m]) return ee.Reducer[simple[m]]();
		if (m === CV) return ee.Reducer.mean().combine(ee.Reducer.stdDev(), '', true);
		var p = /^p(\d+(?:\.\d+)?)$/.exec(m);
		if (p && Number(p[1]) <= 100) return ee.Reducer.percentile([Number(p[1])]);
		throw new Error('unknown metric ' + metric + ': use ' + METRICS);
	}

	// composite.check_metric: error if METRIC is not valid (without Earth Engine)
	function checkMetric(metric) {
		var m = String(metric).trim().toLowerCase();
		if (SIMPLE.indexOf(m) >= 0 || m === DAYS) return;
		var p = /^p(\d+(?:\.\d+)?)$/.exec(m);
		if (!(p && Number(p[1]) <= 100)) throw new Error('unknown metric ' + metric + ': use ' + METRICS);
	}

	// composite.cv: image of the coefficient of variation (%) from the images of the mean and of the standard
	// deviation, masked where the mean is 0 (Earth Engine would give 0 there)
	function cv(mean, std) {
		mean = ee.Image(mean);
		return ee.Image(std).divide(mean).multiply(100).updateMask(mean.neq(0));
	}

	// composite.ee_value_of: the statistic STAT of a region from the feature F of the result of reducer(STAT) over it:
	// the output OUT, or, for the coefficient of variation, 100 × stdDev / mean (null without them or with a mean of 0)
	function statValue(f, stat, out, prefix) {
		f = ee.Feature(f);
		prefix = prefix || '';
		if (!isCv(stat)) return f.get(ee.String(prefix).cat(out));
		var mean = f.get(prefix + 'mean'), std = f.get(prefix + 'stdDev');
		return ee.Algorithms.If(mean, ee.Algorithms.If(std, ee.Number(std).multiply(100).divide(mean), 0), null);
	}

	// composite.cv_number: the coefficient of variation (%) of the evaluated MEAN and STD, or null
	function cvNumber(mean, std) {
		if (mean === null || mean === undefined || std === null || std === undefined || mean === 0) return null;
		return 100 * std / mean;
	}

	// composite.check_rgb_metric: error if METRIC does not give the true colour of the images (see RGB_METRICS)
	function checkRgbMetric(metric) {
		checkMetric(metric);
		var m = String(metric).trim().toLowerCase();
		if (['mean', 'median', 'min', 'max'].indexOf(m) < 0 && m.charAt(0) !== 'p') {
			throw new Error('the true colour of the images takes the metrics ' + RGB_METRICS + ', not ' + metric +
				': the ' + m + ' of the red, green and blue bands is not a colour');
		}
	}

	// composite._md: date of MM-DD in YEAR (29 February is the 28th in common years)
	function md(year, text) {
		var p = String(text).split('-');
		var month = Number(p[0]);
		return ymd(year, month, Math.min(Number(p[1]), daysInMonth(year, month)));
	}

	// composite.windows: [year, first day, day after the last] of each year of PERIOD, or of each season of each year
	function windows(period, season) {
		var start = date(period[0]), end = date(period[1]);
		if (end < start) throw new Error('period ' + period.join(' / ') + ': the end is before the start');
		var out = [];
		for (var y = start.getUTCFullYear() - (season ? 1 : 0); y <= end.getUTCFullYear(); y++) {
			var ws, we;
			if (season) {
				ws = md(y, season[0]);
				we = md(y, season[1]);
				if (we < ws) we = md(y + 1, season[1]);
			} else {
				ws = ymd(y, 1, 1);
				we = ymd(y, 12, 31);
			}
			ws = maxDate(ws, start);
			we = minDate(we, end);
			if (ws <= we) out.push([y, ws, addDays(we, 1)]);
		}
		if (!out.length) throw new Error('no day of the season ' + season + ' in the period ' + period.join(' / '));
		return out;
	}

	// composite.bins: [month, first day, day after the last] of the months or 16 days periods of a window
	function bins(win, temporal) {
		var out = [];
		var d = win[1], we = win[2];
		while (d < we) {
			var nxt = temporal === 'monthly' ? ymd(d.getUTCFullYear(), d.getUTCMonth() + 2, 1) : addDays(d, 16);
			out.push([d.getUTCMonth() + 1, d, minDate(nxt, we)]);
			d = nxt;
		}
		return out;
	}

	// composite._reduce: image of COL reduced with RED (a metric, or an ee.Reducer), with the bands BANDS (one, 'value',
	// by default), all masked if COL is empty. With MOSAIC ('max' or 'min'), the bands of the image where the first band
	// is highest or lowest on each pixel instead (the true colour of the date of the maximum or minimum of the variable)
	function reduce(col, red, bands, mosaic) {
		bands = bands || ['value'];
		var empty = ee.Image.constant(bands.length > 1 ? bands.map(function () { return 0; }) : 0).toFloat()
			.rename(bands).updateMask(0);
		var out;
		if (typeof red === 'string' && isCv(red)) {  // one band: the true colour refuses it (checkRgbMetric)
			var both = col.reduce(reducer(CV));  // bands <band>_mean and <band>_stdDev
			return ee.Image(ee.Algorithms.If(col.size().gt(0), cv(both.select(0), both.select(1)).rename(bands), empty));
		}
		if (typeof red === 'string') red = reducer(red);
		if (mosaic === 'max') {
			out = col.qualityMosaic(bands[0]).select(bands);
		} else if (mosaic === 'min') {
			var low = col.map(function (i) {
				return ee.Image(i).addBands(ee.Image(i).select(bands[0]).multiply(-1).rename('_low'));
			});
			out = low.qualityMosaic('_low').select(bands);
		} else {
			out = col.reduce(red).rename(bands);
		}
		return ee.Image(ee.Algorithms.If(col.size().gt(0), out, empty));
	}

	function asDate(d) {
		return d instanceof Date ? d : date(d);
	}

	// composite.days: image ('value') of the snow cover days of the images of COL (100 = snow, 0 = no snow) between
	// START and END (dates or 'YYYY-MM-DD', END excluded): the sum over the calendar months of the window of the mean of
	// the images of each month / 100 x the days of that month in the window; a month without images on a pixel takes
	// the mean of the others weighted by their days; masked where no month has an image
	function days(col, start, end) {
		start = asDate(start);
		end = asDate(end);
		var snow = [], seen = [];
		bins([null, start, end], 'monthly').forEach(function (b) {
			var n = Math.round((b[2] - b[1]) / 86400000);
			var mean = reduce(col.filterDate(iso(b[1]), iso(b[2])), 'mean');
			snow.push(mean.multiply(n / 100));
			seen.push(ee.Image.constant(n).toFloat().rename('value').updateMask(mean.mask()));
		});
		var weighted = ee.ImageCollection.fromImages(snow).sum();
		var observed = ee.ImageCollection.fromImages(seen).sum();
		return weighted.divide(observed).multiply(Math.round((end - start) / 86400000)).updateMask(observed.gt(0))
			.toFloat().rename('value');
	}

	// composite.spans: [first day, day after the last] of the spans over which the snow cover days of PERIOD are
	// averaged with temporal 'period': its seasons, or, without a season, the spans of 12 months from its first day
	function spans(period, season) {
		if (season) return windows(period, season).map(function (w) { return [w[1], w[2]]; });
		var start = date(period[0]), end = addDays(date(period[1]), 1);
		var out = [], d = start, k = 1;
		while (d < end) {
			var y = start.getUTCFullYear() + k, m = start.getUTCMonth() + 1;
			var nxt = ymd(y, m, Math.min(start.getUTCDate(), daysInMonth(y, m)));
			out.push([d, minDate(nxt, end)]);
			d = nxt;
			k++;
		}
		return out;
	}

	// composite.reduce_span: image of the images of COL between START and END (dates or 'YYYY-MM-DD', END excluded)
	// reduced with RED (see reduce), or, for the snow cover days ('days'), their days (see days)
	function reduceSpan(col, red, start, end, bands, mosaic) {
		if (isDays(red)) {
			if (bands && bands.length > 1) throw new Error('the snow cover days have no true colour');
			return days(col, start, end);
		}
		return reduce(col.filterDate(iso(asDate(start)), iso(asDate(end))), red, bands, mosaic);
	}

	// composite.date_filter
	function dateFilter(wins) {
		var filters = wins.map(function (w) {
			return ee.Filter.date(iso(w[1]), iso(w[2]));
		});
		return filters.length === 1 ? filters[0] : ee.Filter.or.apply(null, filters);
	}

	// composite._mosaic: the mosaic of METRIC for an image with BANDS (see reduce): only for the true colour, whose
	// first band is the variable
	function mosaic(metric, bands) {
		var m = String(metric).trim().toLowerCase();
		return bands.length > 1 && MOSAICS.indexOf(m) >= 0 ? m : null;
	}

	// composite.composite: one image of the collection COL of images of PERIOD, with one band, 'value', or with BANDS,
	// the variable ('value') and its true colour (red, green, blue)
	function composite(col, metric, temporal, interannual, period, season, bands) {
		bands = bands || ['value'];
		var wins = windows(period, season);
		checkMetric(metric);
		var red = metric, mos = mosaic(metric, bands);
		if (temporal === 'period') {
			if (isDays(metric)) {  // the snow cover days: the mean of those of each season or year
				return reduce(ee.ImageCollection.fromImages(spans(period, season).map(function (sp) {
					return days(col, sp[0], sp[1]);
				})), 'mean');
			}
			return reduce(col.filter(dateFilter(wins)), red, bands, mos);
		}
		checkMetric(interannual);
		var red2 = interannual, mos2 = mosaic(interannual, bands);
		if (temporal === 'annual') {
			var years = wins.map(function (w) {
				return reduceSpan(col, red, w[1], w[2], bands, mos);
			});
			return reduce(ee.ImageCollection.fromImages(years), red2, bands, mos2);
		}
		if (temporal !== 'monthly' && temporal !== '16-day') {
			throw new Error('unknown temporal aggregation ' + temporal + ': use ' + TEMPORAL.join(', '));
		}
		var parts = {};
		wins.forEach(function (w) {
			bins(w, temporal).forEach(function (b) {
				(parts[b[0]] = parts[b[0]] || []).push(reduceSpan(col, red, b[1], b[2], bands, mos));
			});
		});
		var months = Object.keys(parts).map(Number).sort(function (a, b) { return a - b; }).map(function (m) {
			return reduce(ee.ImageCollection.fromImages(parts[m]), red2, bands, mos2);
		});
		// the snow cover days of a season are those of its months, summed
		return reduce(ee.ImageCollection.fromImages(months), isDays(metric) ? 'sum' : 'mean', bands);
	}

	// Sensors: quality masks, scale and offset, formula (sensors.py) ------------------------------------------------

	var LANDSAT_57 = {SR_B1: 'blue', SR_B2: 'green', SR_B3: 'red', SR_B4: 'nir', SR_B5: 'swir1', SR_B7: 'swir2',
		ST_B6: 'st', QA_PIXEL: 'QA_PIXEL'};
	var LANDSAT_89 = {SR_B2: 'blue', SR_B3: 'green', SR_B4: 'red', SR_B5: 'nir', SR_B6: 'swir1', SR_B7: 'swir2',
		ST_B10: 'st', QA_PIXEL: 'QA_PIXEL', SR_QA_AEROSOL: 'SR_QA_AEROSOL'};
	var LANDSAT = [  // collection, bands, last date
		['LANDSAT/LT05/C02/T1_L2', LANDSAT_57, null],
		['LANDSAT/LE07/C02/T1_L2', LANDSAT_57, '2003-06-01'],
		['LANDSAT/LC08/C02/T1_L2', LANDSAT_89, null],
		['LANDSAT/LC09/C02/T1_L2', LANDSAT_89, null]
	];
	var CLOUD_SCORE = 'GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED';
	// sensors.RGB: the true colour (RGB) of the images of a variable, the red, green and blue surface reflectance bands
	// of each sensor with their scale and offset (reflectance = raw value x scale + offset). Sentinel-2 L2A: B4, B3, B2;
	// Landsat Collection 2 Level-2: those named red, green and blue by rawCollection; MODIS daily surface reflectance
	// (MOD09GA, MYD09GA, those of the cloud frequency): sur_refl_b01, b04, b03. The other MODIS products, the climate
	// and the fixed layers have no true colour
	var RGB = {
		'Sentinel-2': [['B4', 'B3', 'B2'], 0.0001, 0.0],
		'Landsat': [['red', 'green', 'blue'], 2.75e-05, -0.2],
		'MODIS/061/MOD09GA': [['sur_refl_b01', 'sur_refl_b04', 'sur_refl_b03'], 0.0001, 0.0],
		'MODIS/061/MYD09GA': [['sur_refl_b01', 'sur_refl_b04', 'sur_refl_b03'], 0.0001, 0.0]
	};
	var RGB_BANDS = ['red', 'green', 'blue'];  // sensors.RGB_BANDS: the bands of the true colour, in this order
	var SCENE_CLOUDS ={'Sentinel-2': 'CLOUDY_PIXEL_PERCENTAGE', 'Landsat': 'CLOUD_COVER_LAND'};
	var QUALITY = {clouds: true, water: true, snow: true, aerosols: true, cloud_score: 0.6, scene_clouds: null};
	var FILTERS = ['clouds', 'water', 'snow', 'aerosols'];
	var MEASURES = {water: ['NDWI', 'Chl-a', 'NDCI'], snow: ['NDSI', 'SCF', 'SCD'], aerosols: ['ARSL']};
	var S2_SCL = {clouds: [3, 8, 9, 10], water: [6], snow: [11]};
	// sensors.SCF: the rules of the snow of the snow cover frequency (SCF) of Landsat
	var SCF = {ndsi: 0.35, green: 0.1, nir: 0.1, toa_green: 0.08, min_elevation: 1500, shadow_reach: 70,
		scene_clouds: 80, dem: 'USGS/SRTMGL1_003'};
	var SCF_TOA = {  // sensors.SCF_TOA: TOA collection of each Landsat collection, with its green and SWIR1 bands
		'LANDSAT/LT05/C02/T1_L2': ['LANDSAT/LT05/C02/T1_TOA', ['B2', 'B5']],
		'LANDSAT/LE07/C02/T1_L2': ['LANDSAT/LE07/C02/T1_TOA', ['B2', 'B5']],
		'LANDSAT/LC08/C02/T1_L2': ['LANDSAT/LC08/C02/T1_TOA', ['B3', 'B6']],
		'LANDSAT/LC09/C02/T1_L2': ['LANDSAT/LC09/C02/T1_TOA', ['B3', 'B6']]
	};
	var SCF_FILTERS = ['clouds', 'water'];  // fixed: the SCF is the % of the clear observations (see fixedFilters)

	var CF_CLOUD_SCORE = 0.6;  // sensors.CF_CLOUD_SCORE

	// sensors.TWI: the topographic wetness index (TWI) of MERIT Hydro, ln(a / tan β): the upstream area of MERIT Hydro
	// is in km² (area_scale: m² in a km²), and tan β is at least min_tan_slope on the flats (see twiImage)
	var TWI = {area_scale: 1e6, min_tan_slope: 0.001};

	// catalog.THEMES: the themes of the menu, each with its variables (indices) and its own analyses
	function themes() {
		return CATALOG.themes || [];
	}

	// catalog.OTHER_THEMES: the themes of the menu for the data of Earth Engine outside the catalog, after those of the
	// catalog: any image or collection of images by its ID (earth_engine) and the GEE Community Catalog (community)
	function otherThemes() {
		return CATALOG.other_themes || [];
	}

	// catalog.RATE and catalog.RATE_UDUNITS: a rate per month or per day, whose sum is a total: in the catalog
	// ('[mm/month]', '[mm/day]') and in UDUNITS (the data of Earth Engine outside the catalog: 'mm month-1', 'mm day-1');
	// in UDUNITS also per period of its images, the total of N days of each one ('mm (5 day)-1' of CHIRPS PENTAD,
	// 'kg m-2 (8 day)-1' of an 8-day product, written '/N days' too) and 'd-1'. The units of the catalog keep their own
	var RATE = /^(\[)(.+?)(?:\/(?:month|day)| (?:month|day)-1)(\])$/;
	var RATE_UDUNITS = /^()(.+?)(?:\/(?:month|day|d|\d+ ?days?|\(\d+ ?days?\))| (?:month|day|d|\(\d+ ?days?\))-1)()$/;

	// catalog.unit_of: the unit of the values of ENTRY aggregated with METRIC (and between the years with INTERANNUAL,
	// if they are), then over a region with STAT: the coefficient of variation of any of them is in % ('[%]', '%' in
	// UDUNITS); the sum of a rate (RATE, RATE_UDUNITS: '[mm/month]', e.g. the annual precipitation; 'mm month-1',
	// 'mm (5 day)-1') is a total ('[mm]', 'mm')
	function unitOf(entry, metric, interannual, stat) {
		var text = String(entry.unit || '');
		if (isCv(metric) || isCv(interannual) || isCv(stat)) return text.charAt(0) === '[' ? '[%]' : '%';
		var m = (text.charAt(0) === '[' ? RATE : RATE_UDUNITS).exec(text);
		return m && String(metric || '').toLowerCase() === 'sum' ? m[1] + m[2] + m[3] : entry.unit;
	}

	// sensors.is_cf: the cloud frequency
	function isCf(entry) {
		return entry.fk === 'cf';
	}

	// sensors.is_scf
	function isScf(entry) {
		return entry.fk === 'scf';
	}

	// sensors.rgb_of: [bands, scale, offset] of the true colour of the images of ENTRY (see RGB), or null if they have
	// none (fixed layers, climate, most MODIS products, the data of Earth Engine outside the catalog) or the variable
	// compares two periods (RBR and RdNBR: see burnSeverity)
	function rgbOf(entry) {
		if (!entry || entry.static || entry.two_periods || entry.custom) return null;
		return RGB[entry.sensor] || RGB[entry.col] || null;
	}

	// sensors._with_rgb: VALUE (the image 'value' of the variable of the image IMG) with the true colour of IMG, the
	// bands red, green and blue (surface reflectance), only on the pixels where VALUE has data, so that they are the
	// same pixels as those of the variable (its pixel filters, its own masks and its formula). Without the RESAMPLE of
	// Python (pixels finer than those of the data), which sensorCollection does not port either
	function withRgb(img, value, entry) {
		var rgb = rgbOf(entry);
		var bands = ee.Image(img).select(rgb[0]).multiply(rgb[1]).add(rgb[2]);
		return value.addBands(bands.toFloat().rename(RGB_BANDS).updateMask(value.mask()));
	}

	// sensors._no_rgb
	function noRgb(entry) {
		return new Error(entry.index + ' (' + entry.sensor + ') has no true colour: only the variables of Sentinel-2 and ' +
			'Landsat and the cloud frequency of MODIS (MOD09GA, MYD09GA) have images with red, green and blue bands');
	}

	// sensors.fixed_filters: pixel filters always on for ENTRY, whatever the quality, or null if they can be chosen;
	// none for the fixed layers without dates (elevation, slope, topographic wetness index, WorldClim), for the cloud
	// frequency and for the data of Earth Engine outside the catalog (they keep their own mask: see variable.py)
	function fixedFilters(entry) {
		if (entry.static || entry.custom || isCf(entry)) return [];
		return isScf(entry) ? FILTERS.filter(function (f) { return SCF_FILTERS.indexOf(f) >= 0; }) : null;
	}

	function bits(band, first, last) {
		last = last === undefined ? first : last;
		return band.rightShift(first).bitwiseAnd(Math.pow(2, last - first + 1) - 1);
	}

	function modisCloudState(qa) {
		var state = bits(qa, 3, 4);  // 0 clear, 1 cloudy, 2 mixed, 3 not set (assumed clear)
		return state.eq(0).or(state.eq(3));
	}

	// sensors._modis_09_clouds: MOD09GA, MYD09GA state_1km: bits 0-1 clear (0) or assumed clear (3), no cloud shadow
	// (bit 2) and no cloud of the internal algorithm (bit 10)
	function modis09Clouds(qa) {
		var state = bits(qa, 0, 1);
		return state.eq(0).or(state.eq(3)).and(bits(qa, 2).eq(0)).and(bits(qa, 10).eq(0));
	}

	function viClouds(i) {
		var qa = i.select('DetailedQA');
		return i.select('SummaryQA').neq(3).and(bits(qa, 8).eq(0)).and(bits(qa, 10).eq(0)).and(bits(qa, 15).eq(0));
	}

	var VI = {
		clouds: viClouds,
		water: function (i) { return bits(i.select('DetailedQA'), 11, 13).eq(1); },
		snow: function (i) { return i.select('SummaryQA').neq(2).and(bits(i.select('DetailedQA'), 14).eq(0)); },
		aerosols: function (i) { return bits(i.select('DetailedQA'), 6, 7).neq(3); }
	};
	var LST = {clouds: function (i) { return bits(i.select('QC_Day'), 0, 1).eq(0); }};
	var SNOW = {
		valid: ['NDSI_Snow_Cover', 100],
		clouds: function (i) { return i.select('NDSI_Snow_Cover_Class').unmask(0).neq(250); },
		water: function (i) { return i.select('NDSI_Snow_Cover_Class').unmask(0).remap([237, 239], [0, 0], 1); }
	};
	// the daily surface reflectance of MODIS (the RdNBR of MODIS, MOD09GA and MYD09GA), state_1km: bits 0-1 cloud
	// state (0 clear, 3 assumed clear), 2 cloud shadow, 3-5 land/water (1 land), 6-7 aerosols (3 high), 10 internal
	// cloud flag, 15 internal snow mask
	var SURFACE = {
		clouds: function (i) { return modis09Clouds(i.select('state_1km')); },
		water: function (i) { return bits(i.select('state_1km'), 3, 5).eq(1); },
		snow: function (i) { return bits(i.select('state_1km'), 15).eq(0); },
		aerosols: function (i) { return bits(i.select('state_1km'), 6, 7).neq(3); }
	};
	// sensors.GAP_FILLED: collections with a gap-filled version, made once a year: its images up to its last one in the
	// catalog (CATALOG.collections, as the references), and those of the collection after it (MOD16A2.061 begins in
	// 2021, MOD16A2GF.061 covers 2000 to the end of last year)
	var GAP_FILLED = {'MODIS/061/MOD16A2': 'MODIS/061/MOD16A2GF'};
	var PRODUCTS = {
		'MODIS/061/MOD13Q1': VI,
		'MODIS/061/MYD13Q1': VI,
		'MODIS/061/MOD11A1': LST,
		'MODIS/061/MYD11A1': LST,
		'MODIS/061/MOD16A2': {valid: ['ET', 32700],
			clouds: function (i) { return modisCloudState(i.select('ET_QC')); }},
		'MODIS/061/MCD15A3H': {
			valid: ['Lai', 100],
			clouds: function (i) {
				return modisCloudState(i.select('FparLai_QC')).and(bits(i.select('FparExtra_QC'), 4, 6).eq(0));
			},
			water: function (i) { return bits(i.select('FparExtra_QC'), 0, 1).eq(0); },
			snow: function (i) { return bits(i.select('FparExtra_QC'), 2).eq(0); },
			aerosols: function (i) { return bits(i.select('FparExtra_QC'), 3).eq(0); }
		},
		'MODIS/061/MOD10A1': SNOW,
		'MODIS/061/MYD10A1': SNOW,
		'MODIS/061/MCD19A2_GRANULES': {
			clouds: function (i) { return bits(i.select('AOD_QA'), 0, 2).eq(1); },
			water: function (i) { return bits(i.select('AOD_QA'), 3, 4).neq(1); },
			snow: function (i) { return bits(i.select('AOD_QA'), 3, 4).lt(2); }
		},
		'MODIS/061/MCD43A3': {clouds: function (i) {
			return i.select('BRDF_Albedo_Band_Mandatory_Quality_shortwave').eq(0);
		}},
		'MODIS/061/MOD09GA': SURFACE,
		'MODIS/061/MYD09GA': SURFACE
	};

	function withQuality(quality) {
		var q = {};
		for (var k in QUALITY) q[k] = QUALITY[k];
		for (k in quality || {}) q[k] = quality[k];
		return q;
	}

	// sensors.filters: {filter: true/false} of the pixel filters that apply to ENTRY with QUALITY
	function filters(entry, quality) {
		var out = {};
		var fixed = fixedFilters(entry);
		if (fixed) {
			FILTERS.forEach(function (f) { out[f] = fixed.indexOf(f) >= 0; });
			return out;
		}
		quality = withQuality(quality);
		var available;
		if (entry.sensor === 'Sentinel-2') available = ['clouds', 'water', 'snow'];
		else if (entry.sensor === 'Landsat') available = FILTERS;
		else available = FILTERS.filter(function (f) { return (PRODUCTS[entry.col] || {})[f]; });
		FILTERS.forEach(function (f) {
			var on = quality[f];
			if (String(on).toLowerCase() === 'auto') on = (MEASURES[f] || []).indexOf(entry.index) < 0;
			out[f] = Boolean(on) && available.indexOf(f) >= 0;
		});
		return out;
	}

	// sensors.conflicts: filters on for ENTRY that remove what its variable measures (e.g. snow for NDSI)
	function conflicts(entry, quality) {
		var on = filters(entry, quality);
		return FILTERS.filter(function (f) { return on[f] && (MEASURES[f] || []).indexOf(entry.index) >= 0; });
	}

	// sensors.quality_mask
	function qualityMask(img, entry, quality) {
		var on = filters(entry, quality);
		var masks = [];
		if (entry.sensor === 'Sentinel-2') {
			var scl = img.select('SCL');
			['clouds', 'water', 'snow'].forEach(function (f) {
				if (!on[f]) return;
				if (f === 'clouds' && quality.cloud_score !== null && quality.cloud_score !== undefined) {
					masks.push(img.select('cs_cdf').gte(quality.cloud_score));
				} else {
					var classes = S2_SCL[f];
					masks.push(scl.remap(classes, classes.map(function () { return 0; }), 1));
				}
			});
		} else if (entry.sensor === 'Landsat') {
			var qa = img.select('QA_PIXEL');
			if (on.clouds) masks.push(bits(qa, 1, 4).eq(0));  // dilated cloud, cirrus, cloud, cloud shadow
			if (on.snow) masks.push(bits(qa, 5).eq(0));
			if (on.water) masks.push(bits(qa, 7).eq(0));
			if (on.aerosols) masks.push(bits(img.select('SR_QA_AEROSOL'), 6, 7).neq(3));  // level 3 = high
		} else {
			var product = PRODUCTS[entry.col] || {};
			if (product.valid) masks.push(img.select(product.valid[0]).lte(product.valid[1]));
			FILTERS.forEach(function (f) {
				if (on[f]) masks.push(product[f](img));
			});
		}
		if (!masks.length) return null;
		var mask = masks[0];
		for (var i = 1; i < masks.length; i++) mask = mask.and(masks[i]);
		return mask;
	}

	// sensors._with_toa: images of COL with the bands toa_green and toa_swir1 of the same scene in the TOA collection
	function withToa(col, colId, region, start, end) {
		var toaId = SCF_TOA[colId][0], bands = SCF_TOA[colId][1];
		var toa = ee.ImageCollection(toaId).filterBounds(region).filterDate(start, end);
		var same = ee.Filter.equals({leftField: 'system:index', rightField: 'system:index'});
		return ee.ImageCollection(ee.Join.saveFirst('toa').apply(col, toa, same)).map(function (i) {
			i = ee.Image(i);
			return i.addBands(ee.Image(i.get('toa')).select(bands, ['toa_green', 'toa_swir1']));
		});
	}

	// sensors.raw_collection
	function rawCollection(entry, region, start, end, quality) {
		var prop = SCENE_CLOUDS[entry.sensor];
		var scene = quality.scene_clouds;
		function sceneFilter(col) {
			return prop && scene !== null && scene !== undefined ? col.filter(ee.Filter.lte(prop, scene)) : col;
		}
		if (entry.sensor === 'Landsat') {
			var scf = isScf(entry);
			var cols = [];
			LANDSAT.forEach(function (l) {
				var endL = l[2] && l[2] < end ? l[2] : end;
				if (endL <= start) return;
				var c = sceneFilter(ee.ImageCollection(l[0]).filterBounds(region).filterDate(start, endL));
				if (scf) c = c.filter(ee.Filter.lt('CLOUD_COVER', SCF.scene_clouds));
				c = c.select(Object.keys(l[1]), Object.keys(l[1]).map(function (k) { return l[1][k]; }));
				if (!l[1].SR_QA_AEROSOL) {  // Landsat 5 and 7 have no aerosol QA: nothing is removed
					c = c.map(function (i) {
						return i.addBands(ee.Image.constant(0).toUint8().rename('SR_QA_AEROSOL'));
					});
				}
				if (scf) c = withToa(c, l[0], region, start, endL);
				cols.push(c);
			});
			var col = cols[0];
			for (var i = 1; i < cols.length; i++) col = col.merge(cols[i]);
			return col;
		}
		var out = sceneFilter(ee.ImageCollection(entry.col).filterBounds(region).filterDate(start, end));
		if (GAP_FILLED[entry.col]) {  // the gap-filled images, and those of the collection after the last of them
			var last = ee.Date(CATALOG.collections[GAP_FILLED[entry.col]].end).millis();  // as the references
			out = sceneFilter(ee.ImageCollection(GAP_FILLED[entry.col]).filterBounds(region).filterDate(start, end))
				.filter(ee.Filter.lte('system:time_start', last)).merge(out.filter(ee.Filter.gt('system:time_start', last)));
		}
		if (entry.sensor === 'Sentinel-2' && filters(entry, quality).clouds && quality.cloud_score !== null &&
				quality.cloud_score !== undefined) {
			out = out.linkCollection(ee.ImageCollection(CLOUD_SCORE), ['cs_cdf']);
		}
		return out;
	}

	// sensors.collection: single band images ('value', float) of the variable of ENTRY between START and END (excluded);
	// with RGB, each image also has the bands red, green and blue of its true colour on the same pixels (see withRgb)
	function sensorCollection(entry, region, start, end, quality, rgb) {
		if (rgb && !rgbOf(entry)) throw noRgb(entry);
		quality = withQuality(quality);
		if (isScf(entry)) return scfCollection(entry, region, start, end, quality, rgb);
		if (isCf(entry)) return cfCollection(entry, region, start, end, quality, rgb);
		var scale = number(entry.scale, 1), offset = number(entry.offset, 0);
		var used = entry.fk === 'nd' ? entry.fb : Object.keys(entry.fb).map(function (k) { return entry.fb[k]; })
			.filter(function (b, i, a) { return a.indexOf(b) === i; }).sort();
		return rawCollection(entry, region, start, end, quality).map(function (img) {
			img = ee.Image(img);
			var data = img.select(used).multiply(scale).add(offset);
			var mask = qualityMask(img, entry, quality);
			if (mask) data = data.updateMask(mask);
			var out;
			if (entry.fk === 'nd') {
				out = data.normalizedDifference(entry.fb);
			} else {
				var names = {};
				for (var name in entry.fb) names[name] = data.select(entry.fb[name]);
				out = data.expression(entry.ft, names);
			}
			out = out.toFloat().rename('value');
			if (rgb) out = withRgb(img, out, entry);
			return out.copyProperties(img, ['system:time_start']);
		});
	}

	// sensors.cf_collection: the clouds of the cloud frequency, 100 where the cloud flags of an image say cloud, 0
	// where they say clear, masked where it has no data (with RGB, also the true colour of each image on those pixels:
	// no pixel filters, the clouds are in it)
	function cfCollection(entry, region, start, end, quality, rgb) {
		var col, compute;
		if (entry.sensor === 'Sentinel-2') {
			col = ee.ImageCollection(entry.col).filterBounds(region).filterDate(start, end)
				.linkCollection(ee.ImageCollection(CLOUD_SCORE), ['cs_cdf']);
			compute = function (img) { return img.select('cs_cdf').lt(CF_CLOUD_SCORE).multiply(100); };
		} else if (entry.sensor === 'Landsat') {
			col = rawCollection(entry, region, start, end, quality);
			compute = function (img) {
				var qa = img.select('QA_PIXEL');
				return bits(qa, 3).eq(1).or(bits(qa, 9).eq(1)).multiply(100).updateMask(bits(qa, 0).eq(0));
			};
		} else {  // MODIS
			col = ee.ImageCollection(entry.col).filterBounds(region).filterDate(start, end);
			compute = function (img) {
				var state = bits(img.select('state_1km'), 0, 1);
				return state.eq(1).or(state.eq(2)).multiply(100);
			};
		}
		return col.map(function (img) {
			img = ee.Image(img);
			var out = compute(img).toFloat().rename('value');
			if (rgb) out = withRgb(img, out, entry);
			return out.copyProperties(img, ['system:time_start']);
		});
	}

	// sensors.scf_collection: the snow of the SCF, 100 where a valid observation has snow, 0 where it has none (with
	// RGB, also its true colour on those pixels)
	function scfCollection(entry, region, start, end, quality, rgb) {
		if (entry.sensor === 'Modis') return modisScfCollection(entry, region, start, end, quality, rgb);
		var green = entry.fb[0], nir = entry.fb[1], swir1 = entry.fb[2];
		var scale = number(entry.scale, 1), offset = number(entry.offset, 0);
		var dem = ee.Image(SCF.dem);
		var high = dem.gte(SCF.min_elevation);
		return rawCollection(entry, region, start, end, quality).map(function (img) {
			img = ee.Image(img);
			var sr = img.select([green, nir, swir1]).multiply(scale).add(offset);
			var toa = img.select(['toa_green', 'toa_swir1']);
			var g = sr.select(green), n = sr.select(nir), s = sr.select(swir1);
			var snowSun = g.subtract(s).divide(g.add(s)).gte(SCF.ndsi).and(g.gt(SCF.green)).and(n.gt(SCF.nir));
			var tg = toa.select('toa_green'), ts = toa.select('toa_swir1');
			var snowShade = tg.subtract(ts).divide(tg.add(ts)).gte(SCF.ndsi).and(tg.gte(SCF.toa_green));
			var zenith = ee.Number(90).subtract(ee.Number(img.get('SUN_ELEVATION')));
			var lit = ee.Terrain.hillShadow(dem, ee.Number(img.get('SUN_AZIMUTH')), zenith, SCF.shadow_reach, true);
			var shade = lit.not();
			var qa = img.select('QA_PIXEL');
			var clear = bits(qa, 3).eq(0).and(bits(qa, 9).eq(0));  // its fixed filters (SCF_FILTERS): clouds and water
			var dry = bits(qa, 7).eq(0);
			var validSun = lit.and(clear).and(dry).and(snowSun.mask());
			var validShade = shade.and(high).and(clear.unmask(0)).and(snowShade.mask());
			var snow = snowSun.unmask(0).and(lit).or(snowShade.unmask(0).and(shade));
			var valid = validSun.unmask(0).or(validShade.unmask(0));
			var out = snow.multiply(100).updateMask(valid).toFloat().rename('value');
			if (rgb) out = withRgb(img, out, entry);
			return out.copyProperties(img, ['system:time_start']);
		});
	}

	// sensors._modis_scf_collection: the SCF of MODIS, 100 where NDSI_Snow_Cover >= 100 x SCF.ndsi, 0 below, masked
	// where the daily snow product has a flag (clouds, water, night...: its fixed filters and the valid range of SNOW)
	function modisScfCollection(entry, region, start, end, quality, rgb) {
		if (rgb) throw noRgb(entry);
		var band = entry.fb[0];
		return rawCollection(entry, region, start, end, quality).map(function (img) {
			img = ee.Image(img);
			var snow = img.select(band).gte(SCF.ndsi * 100).multiply(100);
			var mask = qualityMask(img, entry, quality);
			var out = (mask ? snow.updateMask(mask) : snow).toFloat().rename('value');
			return out.copyProperties(img, ['system:time_start']);
		});
	}

	// Data of Earth Engine outside the catalog (assets.py, community.py and variable.py) ------------------------------

	var ASSET_TYPES = {Image: 'image', IMAGE: 'image', ImageCollection: 'image_collection',
		IMAGE_COLLECTION: 'image_collection'};  // assets.TYPES, also with the names of ee.data.getAsset of the Code Editor
	var TABLES = ['Table', 'TABLE', 'FeatureView', 'FEATURE_VIEW'];
	var FOLDERS = ['Folder', 'FOLDER'];
	var DATA_CATALOG = 'Earth Engine data catalog', COMMUNITY_CATALOG = 'GEE Community Catalog',
		EE_ASSET = 'Earth Engine asset';  // the sources of assets.describe
	var CATALOG_PAGE = 'https://developers.google.com/earth-engine/datasets/catalog/';  // assets.PAGE
	var LEGACY = 'projects/earthengine-legacy/assets/';
	// catalog.UDUNITS_TEXT: a unit written in UDUNITS ('mm', 'degC', 'kg m-2', 'mm day-1', '1')
	var UDUNITS_TEXT = /^[A-Za-z0-9 ._^()*\/%+-]+$/;
	// assets.UNITS: the units of the bands of the STAC records of the Earth Engine data catalog (gee:units) in UDUNITS,
	// which the unit given is translated from too (the page of a dataset writes them so: 'W/m^2', '°C', 'mm/d')
	var UNITS = {
		'mm': 'mm', 'cm': 'cm', 'm': 'm', 'km': 'km', 'K': 'K', '&deg;C': 'degC', '°C': 'degC', 'C': 'degC',
		'&deg;F': 'degF', 'deg': 'degree', 'degrees': 'degree', 'rad': 'rad', '%': '%', 'Dimensionless': '1',
		'dimensionless': '1', 'unitless': '1', 'Fraction': '1', 'fraction': '1', 'Area fraction': '1',
		'Volume fraction': '1', 'Mass fraction': '1', 'Mol fraction': '1', 'Spectral reflectance': '1',
		'Reflectance factor': '1', 'index': '1', 'Coefficient of Variation': '1', 'count': '1', 'm/s': 'm s-1',
		'm/s^2': 'm s-2', 'm^2/s': 'm2 s-1', 'm^2/s^2': 'm2 s-2', 'm^2 s-2': 'm2 s-2', '1/s': 's-1', 's^-1': 's-1',
		'm^-1': 'm-1', '1/m': 'm-1', 'Pa': 'Pa', 'hPa': 'hPa', 'kPa': 'kPa', 'mbar': 'mbar', 'Pa/s': 'Pa s-1',
		'W/m^2': 'W m-2', 'J/m^2': 'J m-2', 'J/m^2/day': 'J m-2 day-1', 'MJ m^-2 day^-1': 'MJ m-2 day-1', 'J/kg': 'J kg-1',
		'kg/m^2': 'kg m-2', 'kg/m^2/s': 'kg m-2 s-1', 'kg/m^2/8day': 'kg m-2 (8 day)-1', 'kg/m^3': 'kg m-3',
		'g/m^2': 'g m-2', 'g/cm^3': 'g cm-3', 'g/kg': 'g kg-1', 'kg/kg': 'kg kg-1', 'mg/m^3': 'mg m-3',
		'mg/m^3/day': 'mg m-3 day-1', 'mol/m^2': 'mol m-2', 'mol/m^3': 'mol m-3', 'mmol/m^3': 'mmol m-3',
		'cm^3/cm^3': 'cm3 cm-3', 'm^2/m^3': 'm2 m-3', 'Mg/ha': 'Mg ha-1', 'tonnes/hectare': 'Mg ha-1', 'm^2': 'm2',
		'km^2': 'km2', 'ha': 'ha', 'm^3': 'm3', 'mm/d': 'mm day-1', 'mm/day': 'mm day-1', 'mm, daily total': 'mm day-1',
		'mm/hr': 'mm h-1', 'mm/h': 'mm h-1', 'm/h': 'm h-1', 'mm/month': 'mm month-1', 'mm/y': 'mm year-1',
		'mm/pentad': 'mm (5 day)-1', 'meter/year': 'm year-1', 'm of water equivalent': 'm', 'gpm': 'm', 'h': 'h',
		'min': 'min', 's': 's', 'seconds': 's', 'd': 'day', 'y': 'year', 'ppm': 'ppm', 'ppb': 'ppb', '&mu;m': 'um',
		'&micro;m': 'um', 'MW': 'MW', 'dB': 'dB'
	};
	// variable.UNIT_WORDS: units given in other words, in UDUNITS (before those of UNITS)
	var UNIT_WORDS = {'°C': 'degC', '°F': 'degF', '°': 'degree', 'deg C': 'degC', 'deg F': 'degF'};
	// variable.DIMENSIONLESS: the names of a unit without dimensions, in any case ('1' in UDUNITS)
	var DIMENSIONLESS = ['unitless', 'dimensionless', 'fraction', 'index'];
	var TERRAIN = ['slope', 'aspect'];  // variable.TERRAIN: of the band of an image (ee.Terrain), in degrees
	// variable.BAND_REDUCERS: how several bands of the data by their ID are combined on each pixel (their sum or mean)
	var BAND_REDUCERS = ['sum', 'mean'];
	var TERRAIN_BANDS = 'terrain is the slope or the aspect of one band (an elevation): give one band, without ' +
		'band_reducer';  // variable.TERRAIN_BANDS

	// assets.normalize: the ID of an asset as the tools take it, without quotes, spaces or a call of the Code Editor
	// around it (ee.ImageCollection("X") is X) and without the prefix of the public catalog
	function assetId(asset) {
		var text = String(asset === null || asset === undefined ? '' : asset).trim();
		var m = /^ee\.(?:Image|ImageCollection)\(\s*['"]([^'"]+)['"]\s*\)\s*;?$/.exec(text);
		if (m) text = m[1];
		text = text.trim().replace(/^['"]+|['"]+$/g, '').trim();
		return text.replace(/^projects\/earthengine-public\/assets\//, '');
	}

	// Python's repr of the text TEXT: the messages of the package quote so what was given ('m', "it's")
	function repr(text) {
		text = String(text);
		if (text.indexOf("'") >= 0 && text.indexOf('"') < 0) return '"' + text + '"';
		return "'" + text.replace(/\\/g, '\\\\').replace(/'/g, "\\'") + "'";
	}

	// variable._udunits_text: UNIT of the data of ASSET as given (not blank: a blank unit is not given, see
	// customEntry), in UDUNITS ('mm', 'degC', '1' if dimensionless), with the words of the STAC records translated ('C'
	// and '°C' are degC, 'W/m^2' is W m-2, 'unitless' or 'Fraction' is 1: see UNITS); an error if it cannot be one, as
	// the code of a variable of the catalog ('NDVI': a name, not a unit)
	function udunitsText(unit, asset) {
		var text = String(unit).replace(/º/g, '°').split(/\s+/).filter(function (x) { return x; }).join(' ');
		if (DIMENSIONLESS.indexOf(text.toLowerCase()) >= 0) return '1';
		if (UNIT_WORDS.hasOwnProperty(text)) text = UNIT_WORDS[text];
		else if (UNITS.hasOwnProperty(text)) text = UNITS[text];  // 'C' alone is coulomb in UDUNITS: here degC
		var code = variables().some(function (e) { return String(e.index).toUpperCase() === text.toUpperCase(); });
		if (code || !UDUNITS_TEXT.test(text)) {
			throw new Error('the unit of ' + asset + " is written in UDUNITS (the units of the CF conventions), e.g. 'mm', " +
				"'degC', 'kg m-2', 'mm day-1' or '1' (dimensionless), not " + repr(unit));
		}
		return text;
	}

	// catalog.custom_unit: the unit in UDUNITS of the data outside the catalog as the results give it, without the
	// brackets of the units of the catalog ('mm'; '[unitless]' if dimensionless, as in the catalog)
	function customUnit(unit) {
		unit = String(unit || '').trim();
		return unit === '1' ? '[unitless]' : unit;
	}

	// variable.bands_of: the bands of BAND, one ('pr'), a list (['aet', 'def']) or a text with commas ('aet, def'), as
	// a list of names without blanks ([] if none)
	function bandsOf(band) {
		if (band === null || band === undefined) return [];
		var items = Array.isArray(band) ? band : String(band).split(',');
		return items.map(function (b) { return String(b).trim(); }).filter(function (b) { return b; });
	}

	// The bands of the entry E (customEntry, or a fixed layer of the catalog: its band)
	function entryBands(e) {
		return e.bands || bandsOf(e.band);
	}

	// variable.band_text: the bands of the entry E in titles: the band ('pr'), or the reducer of several ('sum of aet,
	// def')
	function bandText(e) {
		var bands = entryBands(e);
		if (bands.length < 2) return bands.length ? bands[0] : '';
		return (e.reducer || '?') + ' of ' + bands.join(', ');
	}

	// variable.band_words: the bands of the entry E in sentences: 'band pr', or 'the sum of the bands aet and def'
	function bandWords(e) {
		var bands = entryBands(e);
		if (bands.length < 2) return 'band ' + (bands.length ? bands[0] : '?');
		return 'the ' + (e.reducer || '?') + ' of the bands ' + bands.slice(0, -1).join(', ') + ' and ' +
			bands[bands.length - 1];
	}

	// variable.band_stem: the bands of the entry E in file names: the band ('pr'), the reducer and the bands
	// ('sum_aet_def') or, for more than 3, the reducer, how many and the first and the last ('sum12_jan-dec')
	function bandStem(e) {
		var bands = entryBands(e);
		if (bands.length < 2) return bands.length ? bands[0] : '';
		var reducer = e.reducer || '';
		if (bands.length > 3) return reducer + bands.length + '_' + bands[0] + '-' + bands[bands.length - 1];
		return [reducer].concat(bands).join('_');
	}

	// variable.specs for the kinds collection and image: the entry of the data of Earth Engine of ID O.asset, computed
	// like a variable of the catalog. O.use: 'collection' (images with dates, aggregated in time: fromCollection) or
	// 'image' (a fixed layer without dates: staticImage, the mosaic of the tiles if O.type is 'image_collection'); O.band
	// (one, or several: a list or a text with commas, with O.reducer, 'sum' or 'mean', see variable.check_bands); O.scale
	// and O.offset of its stored values (of each band, before they are combined); O.unit of the values (in UDUNITS);
	// O.terrain ('slope' or 'aspect' of the band, image of one band only, in degrees); O.m, the pixel size of the band
	// (of the first band if several: m, as variable.native_scale, see assetInfo); O.dated, false for a collection whose
	// images have no dates (see assetInfo). An error with what is wrong (no band, several without a reducer, an image
	// or a collection of tiles given as a collection, a unit not in UDUNITS), in the words of the package. Its band is
	// that of variable.specs (a text, or the list of several), with bands (the list) and reducer (null for one band)
	function customEntry(o) {
		var asset = assetId(o.asset);
		if (!asset) throw new Error('give the ID of an image or a collection of images of Earth Engine');
		var bands = bandsOf(o.band);
		if (!bands.length) throw new Error('give the band of ' + asset + ' (one, or several with band_reducer)');
		// variable.check_bands, in its order
		var reducer = String(o.reducer === null || o.reducer === undefined ? '' : o.reducer).trim().toLowerCase();
		if (reducer && BAND_REDUCERS.indexOf(reducer) < 0) {
			throw new Error('unknown band_reducer ' + o.reducer + ': use ' + BAND_REDUCERS.join(', '));
		}
		bands.forEach(function (b, i) {
			if (bands.indexOf(b) < i) throw new Error('band ' + b + ' is given twice: give each band once');
		});
		if (bands.length > 1 && o.terrain) throw new Error(TERRAIN_BANDS);  // the slope of a sum is not of an elevation
		if (bands.length > 1 && !reducer) {
			throw new Error(asset + ": give band_reducer, 'sum' or 'mean', to combine its " + bands.length +
				' bands (' + bands.join(', ') + ') into one value on each pixel');
		}
		if (bands.length === 1 && reducer) {
			throw new Error('band_reducer combines several bands: give two or more in band (a list, or a text with ' +
				'commas)');
		}
		var several = bands.length > 1;
		var use = o.use === 'image' ? 'image' : 'collection';
		// variable.specs, in its order: the terrain, then the unit
		var terrain = o.terrain ? String(o.terrain) : null;  // only for an image, in degrees
		if (terrain && use !== 'image') throw new Error('terrain is for an image (image=, e.g. a DEM), not for a collection');
		if (terrain && TERRAIN.indexOf(terrain) < 0) {
			throw new Error('unknown terrain ' + terrain + ': use ' + TERRAIN.join(', '));
		}
		// variable.given_unit: '' or blank is not given (not dimensionless); with a terrain, degree, whatever the unit of
		// the band (ee.Terrain.slope and aspect give degrees)
		var given = o.unit === null || o.unit === undefined ? '' : String(o.unit).trim();
		var unit = given ? udunitsText(o.unit, asset) : '';
		if (terrain) {
			if (unit && unit !== 'degree') {
				throw new Error('the ' + terrain + ' of ' + asset + " is in degrees: give no unit, or 'degree' (not " +
					repr(o.unit) + ', the unit of its band)');
			}
			unit = 'degree';
		}
		// variable.check_asset, then: what Earth Engine says of the ID (O.type and O.dated, see assetInfo)
		if (use === 'collection' && o.type === 'image') {
			throw new Error(asset + ' is an image, not a collection of images: give it as an image (a fixed layer, ' +
				'without dates: maps, GeoTIFFs and statistics of the region)');
		}
		// the dates of its images filter them, so a collection of tiles without dates (a DEM) given as a collection
		// would have no images at all
		if (use === 'collection' && o.type === 'image_collection' && o.dated === false) {
			throw new Error(asset + ' is a collection of images without dates (tiles): give it as an image (their ' +
				'mosaic, a fixed layer, without dates)');
		}
		var m = Number(o.m);  // of the first band: the pixels of the result
		if (!(m > 0)) {
			throw new Error('the pixel size of the band ' + bands[0] + ' of ' + asset +
				' is unknown: read its ID first');
		}
		return {custom: true, static: use === 'image', image_asset: o.type === 'image', col: asset,
			band: several ? bands : bands[0], bands: bands, reducer: several ? reducer : null,
			scale: number(o.scale, 1) || 1, offset: number(o.offset, 0),  // variable._fixed: float(scale or 1)
			unit: unit ? customUnit(unit) : '', terrain: terrain, m: m, type: o.type || null, use: use};
	}

	// services._title: what names the data of the entry E in the titles: the variable and sensor of the catalog (NDVI
	// Sentinel-2), or the ID and band (or the reducer of its bands, see bandText) of the data of Earth Engine, and its
	// terrain (IDAHO_EPSCOR/TERRACLIMATE pr, IDAHO_EPSCOR/TERRACLIMATE sum of aet, def, COPERNICUS/DEM/GLO30 DEM slope)
	function entryName(e) {
		return e.custom ? [e.col, bandText(e), e.terrain].filter(function (x) { return x; }).join(' ') :
			e.index + ' ' + e.sensor;
	}

	// services._what: what names the data of Earth Engine of the entry E in the names of the files: the end of its ID,
	// its band (or the reducer of its bands, see bandStem) and its terrain (TERRACLIMATE_pr, TERRACLIMATE_sum_aet_def,
	// GLO30_DEM_slope)
	function dataStem(e) {
		return [String(e.col).replace(/\/+$/, '').split('/').pop(), bandStem(e), e.terrain]
			.filter(function (x) { return x; }).join('_');
	}

	// assets._not_readable, for the app: it computes with the Cloud project of the app
	function notReadable(asset, error) {
		return 'Earth Engine has no image or collection ' + asset + ', or this app cannot read it (' + error + '). Check ' +
			"the ID: it is the text between the quotes of ee.Image('...') or ee.ImageCollection('...') in the page of " +
			'the dataset (e.g. IDAHO_EPSCOR/TERRACLIMATE). The data of the Earth Engine catalog and of the GEE Community ' +
			'Catalog are public; private assets need to be shared so that anyone can read them.';
	}

	// assets._asset: an error for the assets that are not images or collections of images (TYPE of ee.data.getAsset)
	function notRaster(asset, type) {
		if (TABLES.indexOf(type) >= 0) {
			return asset + ' is a table (ee.FeatureCollection), not an image: MonitorEO computes images and collections ' +
				'of images (regions are given with region)';
		}
		if (FOLDERS.indexOf(type) >= 0) {
			return asset + ' is a folder: give the ID of an image or a collection of images in it';
		}
		return asset + ' is a ' + type + ', not an image or a collection of images';
	}

	// assets.describe, without the STAC record (the app cannot read it): where the asset ASSET comes from, with A, its
	// metadata of ee.data.getAsset: {source (DATA_CATALOG, COMMUNITY_CATALOG or EE_ASSET), title, page, licence (null if
	// not known: the page says it), theme (of the GEE Community Catalog)}. The IDs without users/ or projects/ are those
	// of the public catalog of Earth Engine
	function assetSource(asset, a) {
		var props = (a && a.properties) || {};
		var title = props['system:title'] || props.title;
		if (!/^(users|projects)\//.test(asset)) {
			return {source: DATA_CATALOG, title: title || asset, page: CATALOG_PAGE + asset.replace(/\//g, '_'),
				licence: null};
		}
		var rec = communityRecord(asset);
		if (rec) return {source: COMMUNITY_CATALOG, title: rec.title, page: rec.docs, licence: rec.license, theme: rec.theme};
		return {source: EE_ASSET, title: title || asset, page: 'https://code.earthengine.google.com/?asset=' + asset,
			licence: null};
	}

	// assets.info for the app: what Earth Engine says of the image or collection ASSET (metadata, without computing
	// pixels), to choose its band and use: done(error, {asset, type ('image' or 'image_collection'), dated (a collection
	// whose images have dates), use ('collection' or 'image', as assets.describe), bands (of the image or of the first
	// image of the collection), scales ({band: pixel size in m, as variable.native_scale}), source, title, page,
	// licence, theme (see assetSource)}). Asynchronous (ee.data.getAsset and evaluate): it never blocks the Code Editor
	function assetInfo(asset, done) {
		asset = assetId(asset);
		ee.data.getAsset(asset, function (a, error) {
			if (error || !a) return done(new Error(notReadable(asset, error || 'no such asset')));
			var type = ASSET_TYPES[a.type];
			if (!type) return done(new Error(notRaster(asset, a.type)));
			var src, size = null;
			if (type === 'image') {
				src = ee.Image(asset);
			} else {
				var col = ee.ImageCollection(asset).limit(1);
				src = ee.Image(col.first());
				size = col.size();
			}
			var names = src.bandNames();
			var meta = ee.Dictionary({
				bands: names,
				scales: ee.Dictionary.fromLists(names, names.map(function (b) {
					return src.select(ee.List([b])).projection().nominalScale();
				})),
				dated: src.propertyNames().contains('system:time_start')
			});
			var request = size ? ee.Algorithms.If(size.gt(0), meta, null) : meta;  // an empty collection has no bands
			request.evaluate(function (m, err) {
				if (err && size) {  // if Earth Engine computes both cases of If, an empty collection fails here (no image)
					return size.evaluate(function (n) {
						done(new Error(n === 0 ? 'the collection ' + asset + ' has no images' : notReadable(asset, err)));
					});
				}
				if (err) return done(new Error(notReadable(asset, err)));
				if (!m) return done(new Error('the collection ' + asset + ' has no images'));
				var dated = type === 'image_collection' && Boolean(m.dated);
				var out = {asset: asset, type: type, dated: dated, use: dated ? 'collection' : 'image', bands: m.bands || [],
					scales: m.scales || {}};
				var from = assetSource(asset, a);
				for (var k in from) out[k] = from[k];
				done(null, out);
			});
		});
	}

	// variable._with_band: the images of COL that have BAND, or all the bands of a list of them (Sentinel-1 has VV and
	// VH, or HH and HV)
	function withBand(col, band) {
		(Array.isArray(band) ? band : [band]).forEach(function (b) {
			col = col.filter(ee.Filter.listContains('system:band_names', b));
		});
		return col;
	}

	// variable._projection: the projection of IMG, that of the first of its BANDS if several (projection() of an image
	// whose bands have different projections fails)
	function projection(img, bands) {
		return bands.length > 1 ? img.select(bands[0]).projection() : img.projection();
	}

	// variable._combine: the bands of IMG combined on each pixel with REDUCER ('sum' or 'mean') into one band, only
	// where every band has data, with the projection PROJ of the first band
	function combine(img, reducer, proj) {
		img = img.updateMask(img.mask().reduce(ee.Reducer.min()));
		return img.reduce(ee.Reducer[reducer]()).setDefaultProjection(proj);
	}

	// variable._from_collection: single band images ('value', float) of the band of the collection of the entry E
	// (customEntry) over REGION between START and END (excluded), with the scale and offset of its stored values,
	// bilinear on output pixels of RES metres finer than those of the data (variable._resample), and the date of each
	// image; several bands: each with the scale and offset, then combined on each pixel (combine), only the images
	// with all of them. No pixel filters: the data keep their own mask
	function fromCollection(e, region, start, end, res) {
		var scale = number(e.scale, 1) || 1, offset = number(e.offset, 0);
		var bilinear = Boolean(res) && res < Number(e.m);
		var bands = entryBands(e);
		var col = ee.ImageCollection(e.col).filterBounds(region).filterDate(start, end);
		return withBand(col, e.band).map(function (img) {
			img = ee.Image(img);
			var out = img.select(e.band).multiply(scale).add(offset);  // each band, before they are combined
			if (bands.length > 1) out = combine(out, e.reducer, projection(img, bands));
			if (bilinear) out = out.resample('bilinear');
			return out.toFloat().rename('value').copyProperties(img, ['system:time_start']);
		});
	}

	// The copy of the index of the GEE Community Catalog in CATALOG.community (build.py, from monitoreo.community):
	// its themes ([English, Spanish]) and licences once, and each dataset as [id, title, 1 if a collection of images (0:
	// an image), theme (its index), page (after community.docs, or the whole URL), licence (its index, or null)]
	function community() {
		return CATALOG.community || {themes: [], licences: [], datasets: [], docs: ''};
	}

	function communityRecordOf(r) {
		var c = community(), page = String(r[4] || '');
		return {id: r[0], title: r[1], type: r[2] ? 'image_collection' : 'image', theme: c.themes[r[3]][0],
			docs: page && !/^https?:\/\//.test(page) ? c.docs + page : page,
			license: r[5] === null || r[5] === undefined ? null : c.licences[r[5]]};
	}

	// community._theme: the index of the theme of the catalog named THEME (in English or in Spanish, case insensitive)
	function communityTheme(theme) {
		var low = String(theme || '').trim().toLowerCase(), names = community().themes;
		for (var i = 0; i < names.length; i++) {
			if (low === names[i][0].toLowerCase() || low === names[i][1].toLowerCase()) return i;
		}
		var found = [];
		names.forEach(function (n, j) {
			if (low && (n[0].toLowerCase().indexOf(low) >= 0 || n[1].toLowerCase().indexOf(low) >= 0)) found.push(j);
		});
		if (found.length === 1) return found[0];
		throw new Error('unknown theme ' + theme + ' of the GEE Community Catalog: use one of ' +
			names.map(function (n) { return n[0]; }).join('; '));
	}

	// community.themes: the themes of the catalog with images or collections of images: [{theme (its name in the
	// catalog), name (in LANG, 'en' or 'es'), datasets (how many)}]
	function communityThemes(lang) {
		var c = community(), counts = {};
		c.datasets.forEach(function (r) { counts[r[3]] = (counts[r[3]] || 0) + 1; });
		var out = [];
		c.themes.forEach(function (n, i) {
			if (counts[i]) out.push({theme: n[0], name: lang === 'es' ? n[1] : n[0], datasets: counts[i]});
		});
		return out;
	}

	// community.datasets of one THEME (its name, see communityTheme; all of them without it): [{id, title, type
	// ('image' or 'image_collection'), theme, docs (its page), license}], in the order of the index
	function communityDatasets(theme) {
		var wanted = theme === null || theme === undefined || theme === '' ? null : communityTheme(theme);
		return community().datasets.filter(function (r) { return wanted === null || r[3] === wanted; })
			.map(communityRecordOf);
	}

	// community.record: the record of the Earth Engine asset ASSET in the catalog (with or without the prefix of the
	// old API), or null
	function communityRecord(asset) {
		var id = String(asset || '').trim().replace(LEGACY, '');
		var rows = community().datasets;
		for (var i = 0; i < rows.length; i++) {
			if (rows[i][0].replace(LEGACY, '') === id) return communityRecordOf(rows[i]);
		}
		return null;
	}

	// Variables (variable.py): a spec is {ref (a variable of the catalog) or entry (data of Earth Engine outside it:
	// customEntry), metric, temporal, interannual, period, season, quality, where} ---------------------------------

	function spec(options) {
		var s = {metric: 'mean', temporal: 'period', interannual: 'mean', season: null, quality: {}};
		for (var k in options) s[k] = options[k];
		s.quality = withQuality(s.quality);
		onlyMetric(s.entry ? s.entry : s.ref === undefined || s.ref === null ? {} : byRef(s.ref), s.metric);
		// variable.specs: a period without images of its data is an Error; one with days without them, a warning
		// (notes, for the results panel)
		if (s.period && (s.ref !== undefined && s.ref !== null || s.entry)) checkPeriod(s);
		return s;
	}

	// Dates and data of the variables (coverage.py): the Earth Engine collections of a variable of the catalog, with the
	// dates of their images and their short titles (CATALOG.coverage, written by build.py from the copy of the index of
	// the Earth Engine data catalog of the package), the check of a period against them and what the charts say of
	// their data («Data: ...»). The data of Earth Engine given by their ID are named by the titles of the indexes of
	// catalog.js, but their dates are not checked: catalog.js has only their years -----------------------------------

	var LEVEL = /\bLevel[- ]?\d[A-Za-z0-9]*(?: \([A-Za-z]+\))?/;  // coverage.LEVEL
	var LONG_TITLE = 70;  // coverage.LONG_TITLE
	var STEP_DAYS = {daily: 1, monthly: 31, yearly: 366, annual: 366};  // coverage.STEP_DAYS
	var NOTES = {warnings: [], data: []};  // coverage.Notes: those of the computation of the panel (see resetNotes)
	var LABEL = '';  // coverage._label: the start of the warnings of checkPeriod (those of a condition of where)

	// coverage.short_title: TITLE of a dataset, short for a chart
	function shortTitle(title) {
		title = String(title || '').split(/\s+/).filter(Boolean).join(' ');
		var i = title.indexOf(': ');
		if (i < 0) return title || null;
		var level = LEVEL.exec(title.slice(i + 2));
		if (level) return title.slice(0, i) + ', ' + level[0];
		return title.length > LONG_TITLE ? title.slice(0, i) : title;
	}

	// coverage.join: WORDS in a sentence, 'a', 'a and b', 'a, b and c'
	function joinWords(words) {
		return words.length < 3 ? words.join(' and ') : words.slice(0, -1).join(', ') + ' and ' + words[words.length - 1];
	}

	// coverage.join_titles: one title for the titles of several datasets of a family ('USGS Landsat 8 and 9 Level 2,
	// Collection 2, Tier 1'), or those that share nothing joined with '; '
	function joinTitles(titles) {
		var unique = [];
		titles.forEach(function (t) { if (t && unique.indexOf(t) < 0) unique.push(t); });
		if (unique.length < 2) return unique.length ? unique[0] : null;
		var words = unique.map(function (t) { return t.split(' '); });
		var n = Math.min.apply(null, words.map(function (w) { return w.length; }));
		var head = 0, tail = 0;
		while (head < n - 1 && words.every(function (w) { return w[head] === words[0][head]; })) head++;
		while (tail < n - head - 1 && words.every(function (w) {
			return w[w.length - 1 - tail] === words[0][words[0].length - 1 - tail];
		})) tail++;
		if (!head && !tail) return unique.join('; ');
		var middles = words.map(function (w) { return w.slice(head, w.length - tail).join(' '); });
		return words[0].slice(0, head).concat([joinWords(middles)], tail ? words[0].slice(words[0].length - tail) : [])
			.join(' ');
	}

	// coverage.text: the data of the datasets IDS named NAME, as the charts and warnings say it
	function dataText(ids, name) {
		return name ? joinWords(ids) + ' (' + name + ')' : joinWords(ids);
	}

	// coverage.title: the short title of the Earth Engine dataset ASSET, from the index of the Earth Engine data catalog
	// or of the GEE Community Catalog of catalog.js, or null
	function assetTitle(asset) {
		var rows = (CATALOG.eecatalog || {}).datasets || [];
		for (var i = 0; i < rows.length; i++) if (rows[i][0] === asset) return shortTitle(rows[i][1]);
		var c = CATALOG.community ? communityRecord(asset) : null;
		return c ? shortTitle(c.title) : null;
	}

	// coverage.parts: [[ID, first day, last day or null, short title]] of the collections of the images of the entry E
	// of the catalog (null if catalog.js has none)
	function coverageParts(e) {
		return ((CATALOG.coverage || {}).collections || {})[e.col] || null;
	}

	// coverage._overlaps: whether PART has images between the days A and B (ISO)
	function overlaps(part, a, b) {
		return (!part[1] || part[1] <= b) && (!part[2] || part[2] >= a);
	}

	// coverage._dates_of: [first day, last day or null if one of them goes on] of the images of the parts FOUND
	function datesOf(found) {
		var starts = found.map(function (p) { return p[1]; }).filter(Boolean).sort();
		var ends = found.map(function (p) { return p[2]; });
		var open = ends.some(function (x) { return !x; });
		return [starts.length ? starts[0] : null, open || !ends.length ? null : ends.slice().sort()[ends.length - 1]];
	}

	function partsText(found) {
		return dataText(found.map(function (p) { return p[0]; }), joinTitles(found.map(function (p) { return p[3]; })));
	}

	// coverage.of_entry (its text): the data of the values of the entry E of the catalog in PERIODS ([[first, last
	// day]]; all its collections without them), e.g. 'COPERNICUS/S2_SR_HARMONIZED (Harmonized Sentinel-2 MSI, Level-2A
	// (SR))'; of the data of Earth Engine by their ID, their ID and title
	function dataSource(e, periods) {
		if (e.custom) return dataText([e.col], assetTitle(e.col));
		var found = coverageParts(e);
		if (!found) return e.col;
		var inside = e.static ? [] : found.filter(function (p) {
			return (periods || []).some(function (q) { return overlaps(p, q[0], q[1]); });
		});
		return partsText(inside.length ? inside : found);
	}

	// coverage.step_days: the days that each image of the entry E covers (its 'tr')
	function stepDays(e) {
		var tr = String(e.tr || '').trim().toLowerCase();
		var m = /^(\d+)\s*-?\s*days?$/.exec(tr);
		return m ? Number(m[1]) : (STEP_DAYS[tr] || 1);
	}

	// coverage._how_long and coverage._missing: 'its first 15 months have no data', 'its last day has no data'
	function howLong(days) {
		var n = days, unit = 'day';
		if (days >= 730) {
			n = Math.round(days / 365.25);
			unit = 'year';
		} else if (days >= 31) {
			n = Math.round(days / 30.4375);
			unit = 'month';
		}
		return n === 1 ? '1 ' + unit : n + ' ' + unit + 's';
	}

	function missing(which, days) {
		var length = howLong(days), one = length.indexOf('1 ') === 0;
		return 'its ' + which + ' ' + (one ? length.slice(2) : length) + ' ' + (one ? 'has' : 'have') + ' no data';
	}

	function noteWarning(text) {
		text = LABEL + text;
		if (NOTES.warnings.indexOf(text) < 0) NOTES.warnings.push(text);
		return text;
	}

	// coverage.check: the period of the spec S of a variable of the catalog against the dates of its images, without
	// Earth Engine: an Error if it has no images (it ends before the first, falls in a gap between collections, or
	// begins after TODAY, by default today, whatever the data); else the warnings of its days without data (the period
	// begins before the first image, or ends, or even begins, after the last image of data that ended, and the days it
	// covers), [texts], each also noted for the results panel (notes). Nothing for the fixed layers and the data by
	// their ID
	function checkPeriod(s, today) {
		var e = entryOf(s);
		var found = e.static || e.custom ? null : coverageParts(e);
		if (!found || !found.some(function (p) { return p[1]; })) return [];
		var wins = windows(s.period, s.season);
		var first = wins[0][1], last = addDays(wins[wins.length - 1][2], -1);
		var a = iso(first), b = iso(last);
		var season = s.season ? ' (in its season)' : '';
		today = today || iso(new Date());
		if (a > today) {  // whatever the data: also those that ended (the warning below would say they may have images)
			throw new Error('The period asked for' + season + ', ' + a + ' to ' + b + ', begins after today (' + today +
				'): there are no images of ' + partsText(found) + ' for it yet.');
		}
		var dates = datesOf(found), start = dates[0], end = dates[1];
		var inside = found.filter(function (p) { return overlaps(p, a, b); });
		if (!inside.length) {
			var data = partsText(found);
			if (start && b < start) {
				throw new Error('The images of ' + data + ' start on ' + start + ': the period asked for' + season + ', ' + a +
					' to ' + b + ', ends before them and has no data. Choose a period from ' + start + ' on.');
			}
			if (end && a > end) {  // a warning, not an error: the copy of the index may be older than their last images
				return [noteWarning('The images of ' + data + ' end on ' + end + ' (in the copy of the Earth Engine data ' +
					'catalog of ' + (CATALOG.coverage || {}).checked + '): the period asked for' + season + ', ' + a + ' to ' + b +
					', begins after them, so it may have no data, unless Earth Engine has added images since.')];
			}
			var before = found.map(function (p) { return p[2]; }).filter(function (x) { return x && x < a; }).sort();
			var after = found.map(function (p) { return p[1]; }).filter(function (x) { return x && x > b; }).sort();
			if (before.length && after.length) {
				throw new Error('The images of ' + data + ' have none from ' + iso(addDays(date(before[before.length - 1]), 1)) +
					' to ' + iso(addDays(date(after[0]), -1)) + ': the period asked for' + season + ', ' + a + ' to ' + b +
					', has no data. Choose a period before or after those days.');
			}
			return [];
		}
		var out = [], what = partsText(inside);
		if (start && a < start) {
			out.push(noteWarning('The images of ' + what + ' start on ' + start + ': the period asked for' + season +
				' begins on ' + a + ', so ' + missing('first', Math.round((date(start) - first) / 86400000)) + '.'));
		}
		if (end) {
			var covered = addDays(date(end), stepDays(e) - 1);
			if (last > covered) {
				out.push(noteWarning('The images of ' + what + ' end on ' + end + ': the period asked for' + season +
					' ends on ' + b + ', so ' + missing('last', Math.round((last - covered) / 86400000)) + '.'));
			}
		}
		return out;
	}

	// coverage.collect: the notes of a computation of the panel, from its first spec: resetNotes, then notes() gives
	// {warnings, data} (data: [[entry, periods]] of its variables, see used); the panel keeps those of each computation
	// (they are another object after resetNotes)
	function resetNotes() {
		NOTES = {warnings: [], data: []};
	}

	function notes() {
		return NOTES;
	}

	// F() with the notes NOTED (those of the computation that called it, which a newer one may have replaced since:
	// the blocks of a series fetched later), or its error
	function withNotes(noted, f) {
		var current = NOTES;
		NOTES = noted;
		try {
			return f();
		} finally {
			NOTES = current;
		}
	}

	// coverage.used: the values of the computation come from the data of the spec S (in its period)
	function used(s) {
		var e = entryOf(s), key = (e.custom ? 'asset ' : 'entry ') + e.col;
		var item = NOTES.data.filter(function (d) { return d[0] === key; })[0];
		if (!item) {
			item = [key, e, []];
			NOTES.data.push(item);
		}
		if (s.period && !e.static) item[2].push([String(s.period[0]).slice(0, 10), String(s.period[1]).slice(0, 10)]);
	}

	// coverage.source: the data of the values of the computation (of its notes NOTED, default those of now), as its
	// charts say it, or null
	function sourceText(noted) {
		var texts = [];
		(noted || NOTES).data.forEach(function (d) {
			var t = dataSource(d[1], d[2]);
			if (texts.indexOf(t) < 0) texts.push(t);
		});
		return texts.length ? texts.join('; ') : null;
	}

	// variable.specs: error if METRIC is not the only metric of the entry E, if it has one (SCF and CF: the mean of
	// their images). Also for the metric of each step of a series and of each year of the trends (series,
	// yearlyCollection), which the services of Python check as the metric of their spec
	function onlyMetric(e, metric) {
		if (e.metric && String(metric).trim().toLowerCase() !== e.metric) {
			throw new Error(e.index + ' (' + e.sensor + ") only takes the metric '" + e.metric + "'");
		}
		if (e.metric !== DAYS && isDays(metric)) {  // composite.days: only for the snow cover days
			throw new Error("the metric '" + DAYS + "' is that of the snow cover days (variable SCD): " +
				(e.index ? e.index + ' (' + e.sensor + ')' : 'this variable') + ' does not take it');
		}
	}

	function entryOf(s) {
		return s.entry || byRef(s.ref);
	}

	function span(s) {
		var wins = windows(s.period, s.season);
		return [iso(wins[0][1]), iso(wins[wins.length - 1][2])];
	}

	// variable.is_static: a fixed layer without dates: a variable of the catalog without them (elevation, slope) or an
	// image of Earth Engine given as image (customEntry)
	function isStatic(s) {
		return Boolean(entryOf(s).static);
	}

	// variable.check_dates: error if S is a fixed layer without dates, for WHAT needs them
	function checkDates(s, what) {
		if (!isStatic(s)) return;
		var e = entryOf(s);
		what = what || 'time series, trends or comparisons';
		if (e.custom) {
			throw new Error(e.col + ' (' + bandWords(e) + ') is given as a fixed image, without dates (image=): it ' +
				'has maps, GeoTIFFs and statistics of the region (map_layer, download_image, region_stats), but no ' +
				what + '. A collection of images with dates is given as collection=');
		}
		throw new Error(e.index + ' (' + e.sensor + ') is a fixed layer, without dates: it has maps, GeoTIFFs and ' +
			'statistics of the region, but no ' + what);
	}

	// variable._twi: the topographic wetness index (TWI) of the entry E (MERIT Hydro, formula TWI(elv,upa), whose bands
	// are e.fb), ln(a / tan β): a, the upstream drainage area (km²) per metre of contour (at least the area of the
	// pixel, divided by the square root of its area: in m); β, the slope of the elevation (ee.Terrain.slope, in
	// degrees), tan β at least TWI.min_tan_slope (the flats). On the grid of the elevation, so that the bilinear
	// interpolation and the mean of the bigger pixels (staticImage) are those of the TWI, not of the upstream area. The
	// same calls of Earth Engine, in the same order, as the package (tests/test_themes.py compares them)
	function twiImage(e) {
		var src = ee.Image(e.col);
		var elv = src.select(e.fb[0]);
		var px = ee.Image.pixelArea();
		var a = src.select(e.fb[1]).multiply(TWI.area_scale).max(px).divide(px.sqrt());
		var tan = ee.Terrain.slope(elv).multiply(Math.PI / 180).tan().max(TWI.min_tan_slope);
		return a.divide(tan).log().setDefaultProjection(elv.projection());
	}

	// variable._fixed for the fixed layers of the catalog and the images of Earth Engine given as image (customEntry):
	// the image, or the mosaic of the tiles of its collection (several bands: each with the scale and offset, then
	// combined on each pixel, see combine), its terrain (slope or aspect, in degrees), bilinear on pixels RES finer than
	// those of the data and, on pixels RES more than twice as big, the mean of its pixels; the topographic wetness index
	// (formula kind 'twi') from two bands of its image instead (twiImage)
	function staticImage(e, res) {
		var img, proj = null, bands;
		if (e.fk === 'twi') {  // the topographic wetness index, from two bands: no scale, offset or terrain
			img = twiImage(e);
		} else {
			bands = entryBands(e);
			if (e.image_asset) {  // an image (WorldClim), not a collection
				img = ee.Image(e.col).select(e.band);
				if (bands.length > 1) proj = projection(img, bands);
			} else {
				var col = ee.ImageCollection(e.col);
				if (e.custom) col = withBand(col, e.band);  // data by its ID: only the tiles with the band
				col = col.select(e.band);
				img = col.mosaic();
				proj = projection(col.first(), bands);
				img = img.setDefaultProjection(proj);
			}
			img = img.multiply(number(e.scale, 1)).add(number(e.offset, 0));  // e.g. WorldClim, in tenths of a degree
			if (bands.length > 1) img = combine(img, e.reducer, proj);
		}
		// variable._resample: pixels finer than the data; the TWI also on pixels up to twice as big (its default: those of
		// the data), interpolated from the TWI of the grid of MERIT Hydro, not computed on the output pixels
		if (e.fk === 'twi' ? (res || Number(e.m)) <= 2 * Number(e.m) : res && res < Number(e.m)) {
			img = img.resample('bilinear');
		}
		if (e.terrain === 'slope') img = ee.Terrain.slope(img);
		else if (e.terrain === 'aspect') img = ee.Terrain.aspect(img);
		if ((res || Number(e.m)) > 2 * Number(e.m)) img = img.reduceResolution(ee.Reducer.mean(), true, 65535);
		return img.toFloat().rename('value');
	}

	// Land cover masks (landcover.py): the pixels of some broad land covers (water, built...) left out of a result,
	// after a land cover map of a year and the table of correspondences of its classes (CATALOG.landcover): a
	// condition of where, {landcover: map, year, exclude: [broad land covers]} ---------------------------------------

	var LANDCOVER_SHARE = 0.5;  // landcover.SHARE: a pixel is left out when the land covers excluded cover this or more

	function landcoverClasses() {
		return CATALOG.landcover.classes;
	}

	function landcoverMaps() {
		return CATALOG.landcover.maps;
	}

	// landcover.find: the map KEY (its key or its name, in any case, without spaces)
	function landcoverMap(key) {
		var low = function (x) { return String(x).toLowerCase().replace(/[ _-]/g, ''); };
		var maps = landcoverMaps();
		for (var i = 0; i < maps.length; i++) {
			if (low(key) === low(maps[i].key) || low(key) === low(maps[i].name)) return maps[i];
		}
		throw new Error('unknown land cover map ' + key + ': use one of ' +
			maps.map(function (m) { return m.key; }).join(', '));
	}

	// landcover.years: the years of the map M (those of its images, or from its first year to its last or this year)
	function landcoverYears(m) {
		if (m.years) return m.years.map(Number);
		var last = m.last_year || new Date().getFullYear(), out = [];
		for (var y = Number(m.first_year); y <= last; y++) out.push(y);
		return out;
	}

	// landcover.default_year: its last year; for a map of every year until now (Dynamic World), the last whole year
	function landcoverDefaultYear(m) {
		if (m.years || m.last_year) return landcoverYears(m).slice(-1)[0];
		return new Date().getFullYear() - 1;
	}

	function isLandcover(c) {
		return Boolean(c) && c.landcover !== undefined && c.landcover !== null;
	}

	// landcover.check: [map, year, [broad land covers excluded]] of the land cover condition C, or an Error
	function landcoverCheck(c) {
		var m = landcoverMap(c.landcover);
		var year = c.year === undefined || c.year === null || c.year === '' ? landcoverDefaultYear(m) : Number(c.year);
		if (landcoverYears(m).indexOf(year) < 0) throw new Error(m.name + ' has no map of ' + c.year);
		var keys = landcoverClasses().map(function (k) { return k.key; });
		var exclude = [].concat(c.exclude || []);
		if (!exclude.length) {
			throw new Error('a land cover condition of where needs exclude: the land covers to leave out, of ' +
				keys.join(', '));
		}
		exclude.forEach(function (k) {
			if (keys.indexOf(k) < 0) throw new Error('unknown land cover ' + k + ': use ' + keys.join(', '));
		});
		return [m, year, exclude];
	}

	// landcover.codes: the classes (codes) of the map M that are the broad land covers EXCLUDE
	function landcoverCodes(m, exclude) {
		return Object.keys(m.classes).filter(function (code) {
			return exclude.indexOf(m.classes[code]) >= 0;
		}).map(Number).sort(function (a, b) { return a - b; });
	}

	// landcover.source: the image of the classes of the map M of YEAR
	function landcoverSource(m, year, region) {
		if (m.images) return ee.Image(m.images[String(year)]).select(m.band);
		if (m.collections) return ee.ImageCollection(m.collections[String(year)]).first().select(m.band);
		var col = ee.ImageCollection(m.collection).filterDate(year + '-01-01', (year + 1) + '-01-01').select(m.band);
		if (m.composite === 'mode') {  // the most frequent class of the images of the year (Dynamic World)
			if (region) col = col.filterBounds(region);
			return col.mode().setDefaultProjection(col.first().projection());
		}
		return ee.Image(col.first());  // the image of the year (MODIS MCD12Q1)
	}

	// landcover.keep: the image (1) of the pixels of RES metres kept by the land cover condition C, 0 where the land
	// covers excluded cover LANDCOVER_SHARE of the pixel or more, masked where the map has no data
	function landcoverKeep(c, region, res) {
		var x = landcoverCheck(c), m = x[0];
		var codes = landcoverCodes(m, x[2]);
		var excluded = landcoverSource(m, x[1], region).remap(codes, codes.map(function () { return 1; }), 0);
		if (res && res > 2 * Number(m.m)) excluded = excluded.reduceResolution(ee.Reducer.mean(), true, 65535);
		return ee.Image(1).updateMask(excluded.mask()).and(excluded.lt(LANDCOVER_SHARE));
	}

	// landcover.text: the land cover condition C in words, in LANG
	function landcoverText(c, lang) {
		var x = landcoverCheck(c);
		var names = x[2].map(function (k) {
			var cl = landcoverClasses().filter(function (y) { return y.key === k; })[0];
			return (cl[lang] || cl.en).toLowerCase();
		});
		var which = names.length > 1 ? names.slice(0, -1).join(', ') + (lang === 'es' ? ' ni ' : ' or ') +
			names[names.length - 1] : names[0];
		return (lang === 'es' ? 'el uso del suelo no es ' : 'the land cover is not ') + which + ' (' + x[0].name + ' ' +
			x[1] + ')';
	}

	// Categorical layers (categorical.py): fixed layers whose values are class codes, not quantities (the field
	// classes of an entry, the key of its table in CATALOG.classes): the ecoregions (ECOREGION, the ECO_ID of each
	// pixel) and biomes (BIOME) of RESOLVE Ecoregions 2017. The polygons are rasterized once (the ECO_ID of the polygon
	// of each pixel) and the biome comes from it with the table, so both layers have the same boundaries; on pixels more
	// than twice as big as m, the majority class (mode); a condition of where keeps some classes ({ref, classes}) or
	// leaves them out ({ref, exclude}) ------------------------------------------------------------------------------

	var CLASS_SHARE = LANDCOVER_SHARE;  // categorical.SHARE: a pixel is kept when the classes kept cover this or more
	var CLASS_STATS = ['mode', 'count'];  // categorical.STATS: the statistics of a categorical layer over a region
	var CLASS_GAP = 'bdbdbd';  // categorical.GAP: the colour of the codes without a class in the palette of classVis
	var CLASS_EXAMPLE = '{"variable": "BIOME", "sensor": "RESOLVE", "classes": [12]}';  // categorical.EXAMPLE
	var classCache = {};

	// categorical.table: the table of classes KEY ('ecoregions' or 'biomes')
	function classTable(key) {
		return CATALOG.classes[key];
	}

	// categorical.is_categorical: whether the entry E is a categorical layer (it has a table of classes)
	function isCategorical(e) {
		return Boolean(e && e.classes);
	}

	// categorical._rows: {code: {field: value}} of the table KEY (read once)
	function classRows(key) {
		if (!classCache[key]) {
			var t = classTable(key), out = {};
			Object.keys(t.classes).forEach(function (code) {
				var row = {};
				t.fields.forEach(function (f, i) { row[f] = t.classes[code][i]; });
				out[Number(code)] = row;
			});
			classCache[key] = out;
		}
		return classCache[key];
	}

	function uniqueSorted(values) {
		var out = [];
		values.forEach(function (v) {
			v = Math.round(Number(v));
			if (out.indexOf(v) < 0) out.push(v);
		});
		return out.sort(function (a, b) { return a - b; });
	}

	// categorical.codes: the codes of the classes of the categorical entry E, from the lowest
	function classCodes(e) {
		return Object.keys(classRows(e.classes)).map(Number).sort(function (a, b) { return a - b; });
	}

	// categorical.name: the name of the class CODE of E (in Spanish with LANG 'es', if the table has it)
	function categoryName(e, code, lang) {
		var row = classRows(e.classes)[Number(code)];
		if (!row) return String(code);
		return (lang === 'es' && row.name_es) || row.name;
	}

	// categorical.label: the class CODE of E in a legend, «12 Mediterranean Forests, Woodlands & Scrub»
	function categoryLabel(e, code, lang) {
		return Math.round(Number(code)) + ' ' + categoryName(e, code, lang);
	}

	// categorical.colour: the colour of the class CODE of E (hex, without #), CLASS_GAP if it has none
	function categoryColour(e, code) {
		var row = classRows(e.classes)[Number(code)];
		return row ? row.colour : CLASS_GAP;
	}

	// categorical.group_of: the group of the class CODE of E (the biome of an ecoregion), or null
	function categoryGroupOf(e, code) {
		var row = classRows(e.classes)[Number(code)];
		return row && row.group !== undefined ? row.group : null;
	}

	// categorical.group_entry: the categorical entry of the groups of the classes of E (BIOME for ECOREGION), or null
	function categoryGroupEntry(e) {
		var key = classTable(e.classes).group;
		if (!key) return null;
		return variables().filter(function (v) { return v.classes === key && v.col === e.col; })[0] || null;
	}

	// categorical.classes: [{code, name, colour}] of the classes of E and, with groups, group and group_name
	function layerClasses(e, lang) {
		var group = categoryGroupEntry(e), rows = classRows(e.classes);
		return classCodes(e).map(function (code) {
			var row = rows[code];
			var c = {code: code, name: (lang === 'es' && row.name_es) || row.name, colour: row.colour};
			if (group) {
				c.group = row.group;
				c.group_name = categoryName(group, row.group, lang);
			}
			return c;
		});
	}

	// categorical._code: X as the code of a class (an integer), or an Error
	function classCode(x) {
		var text = String(x).trim(), f = Number(text);
		if (text === '' || !isFinite(f) || f !== Math.round(f)) {
			throw new Error('the codes of the classes are whole numbers, e.g. [12]; not ' +
				(typeof x === 'string' ? repr(x) : String(x)));
		}
		return f;
	}

	// categorical.check: VALUES (a code, a list of codes or a text with commas) as the codes of classes of E, each once,
	// in their order; an Error if one is not a code of its table, or if there are none (WHAT: classes or exclude)
	function checkClasses(e, values, what) {
		what = what || 'classes';
		if (typeof values === 'string') {
			values = values.replace(/;/g, ',').split(',').filter(function (v) { return v.trim(); });
		} else if (typeof values === 'number') {
			values = [values];
		}
		if (!Array.isArray(values) || !values.length) {
			throw new Error('the ' + what + ' of ' + e.index + ' (' + e.sensor + ') are a list of codes of its classes, ' +
				'e.g. [12]: list_classes gives them');
		}
		var out = [];
		values.forEach(function (v) {
			var c = classCode(v);
			if (out.indexOf(c) < 0) out.push(c);
		});
		var known = classRows(e.classes);
		var unknown = out.filter(function (c) { return !known.hasOwnProperty(c); });
		if (unknown.length) {
			throw new Error(e.index + ' (' + e.sensor + ') has no classes ' + unknown.join(', ') + ': list_classes gives ' +
				'the codes of its classes');
		}
		return out;
	}

	// categorical._plain: TEXT in lower case without accents, to search the names
	function plainText(text) {
		var s = String(text).toLowerCase();
		return s.normalize ? s.normalize('NFD').replace(/[\u0300-\u036f]/g, '') : s;
	}

	// categorical.find: the classes of E (layerClasses) with every word of TEXT at the start of a word of their code,
	// name (in English or Spanish) or group, at most LIMIT
	function findClasses(e, text, limit, lang) {
		var rows = layerClasses(e, lang);
		if (text !== undefined && text !== null && text !== '') {
			var words = plainText(text).split(/\s+/).filter(function (w) { return w; });
			var group = categoryGroupEntry(e);
			rows = rows.filter(function (c) {
				var names = [String(c.code), c.name, categoryName(e, c.code, 'en'), categoryName(e, c.code, 'es')];
				if (group) names = names.concat([c.group_name || '', categoryName(group, c.group, 'en'), String(c.group)]);
				var all = plainText(names.join(' '));
				return words.every(function (w) {
					return new RegExp('(^|[^a-z0-9])' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).test(all);
				});
			});
		}
		return limit ? rows.slice(0, Number(limit)) : rows;
	}

	// categorical.legend: [{value, label, color ('#rrggbb')}] of the classes VALUES of E (default: all of them), from
	// the lowest code, as the legend of the burn severity
	function categoryLegend(e, values, lang) {
		var codes = values === null || values === undefined ? classCodes(e) : uniqueSorted(values);
		return codes.map(function (v) {
			return {value: v, label: categoryLabel(e, v, lang), color: '#' + categoryColour(e, v)};
		});
	}

	// categorical.vis: {min (the lowest code), max (the highest), palette (the colour of each code from min to max)} of
	// the classes VALUES of E (default: all of them), so that each code gets the colour of its class
	function classVis(e, values) {
		var codes = values && values.length ? uniqueSorted(values) : classCodes(e);
		var lo = codes[0], hi = codes[codes.length - 1], palette = [];
		for (var c = lo; c <= hi; c++) palette.push(categoryColour(e, c));
		if (hi === lo) return {min: lo, max: lo + 1, palette: palette.concat(palette)};  // Earth Engine needs max > min
		return {min: lo, max: hi, palette: palette};
	}

	// categorical._ecoregions: the ECO_ID of each pixel of the dataset of E (the first polygon of the pixel), integer,
	// masked where there is none (ECO_ID 0, Rock and Ice, is a class)
	function ecoregionImage(e) {
		var base = classTable('ecoregions');
		return ee.FeatureCollection(e.col).reduceToImage([base.property], ee.Reducer.first()).toInt();
	}

	// categorical.image: the classes of the categorical entry E (band 'value', integer), rasterized at the output pixel
	// of RES metres and, on pixels more than twice as big as m, the majority class (mode) of its pixels of m
	function categoricalImage(e, res) {
		var img = ecoregionImage(e);
		if (e.classes !== 'ecoregions') {  // the groups of the ecoregions (the biomes), from the ECO_ID of each pixel
			if (classTable('ecoregions').group !== e.classes) {
				throw new Error('the classes of ' + e.index + ' are not those of the ecoregions nor their groups');
			}
			var rows = classRows('ecoregions');
			var ids = Object.keys(rows).map(Number).sort(function (a, b) { return a - b; });
			img = img.remap(ids, ids.map(function (i) { return rows[i].group; }));
		}
		var m = Number(e.m);
		if (res && Number(res) > 2 * m) {
			img = img.setDefaultProjection(ee.Projection('EPSG:4326').atScale(m)).reduceResolution(ee.Reducer.mode(), false,
				65535);
		}
		return img.toInt().rename('value');
	}

	// categorical.present, in two parts: the ee.List of the ECO_ID of the polygons that touch REGION, to evaluate
	// (classesIn), and the codes of the classes of E of those ECO_ID (presentCodes: for the biomes, those of the
	// ecoregions there), from the lowest
	function classesIn(e, region) {
		return ee.FeatureCollection(e.col).filterBounds(region).aggregate_array(classTable('ecoregions').property)
			.distinct();
	}

	function presentCodes(e, ids) {
		var got = uniqueSorted(ids || []);
		if (e.classes === 'ecoregions') return got;
		var rows = classRows('ecoregions');
		return uniqueSorted(got.filter(function (i) { return rows[i]; }).map(function (i) { return rows[i].group; }));
	}

	// categorical.condition: [entry, codes, keep] of the condition C of where on a categorical layer ({ref, classes}:
	// keep true, only the pixels of those classes; {ref, exclude}: keep false, without them); an Error if it is wrong
	function classCondition(c, e) {
		e = e || byRef(c.ref);
		var given = ['classes', 'exclude'].filter(function (k) { return c[k] !== undefined && c[k] !== null; });
		if (!isCategorical(e)) {
			throw new Error('classes and exclude are for a categorical layer (ECOREGION, BIOME): ' + e.index + ' (' +
				e.sensor + ') takes min and max');
		}
		if ((c.min !== undefined && c.min !== null) || (c.max !== undefined && c.max !== null)) {
			throw new Error(e.index + ' (' + e.sensor + ') is a categorical layer, whose values are class codes: a ' +
				'condition on it takes classes (the classes to keep) or exclude (those to leave out), not min or max');
		}
		if (given.length === 2) throw new Error('the condition on ' + e.index + ' of where takes classes or exclude, not both');
		if (!given.length) {
			throw new Error('the condition on ' + e.index + ' of where needs classes (the classes to keep) or exclude ' +
				'(those to leave out), e.g. ' + CLASS_EXAMPLE);
		}
		return [e, checkClasses(e, c[given[0]], given[0]), given[0] === 'classes'];
	}

	// categorical.keep: the image (1) of the pixels of RES metres kept by a condition on the categorical entry E: with
	// KEPT, where the classes VALUES cover CLASS_SHARE of the pixel or more; else, where they cover less; masked where the
	// layer has no data
	function classKeep(e, values, kept, res) {
		var inside = categoricalImage(e).remap(values, values.map(function () { return 1; }), 0);
		var m = Number(e.m);
		if (res && Number(res) > 2 * m) {
			inside = inside.setDefaultProjection(ee.Projection('EPSG:4326').atScale(m)).reduceResolution(ee.Reducer.mean(),
				true, 65535);
		}
		return ee.Image(1).updateMask(inside.mask()).and(kept ? inside.gte(CLASS_SHARE) : inside.lt(CLASS_SHARE));
	}

	// categorical.text: the condition C on a categorical layer in words, in LANG, e.g. «BIOME (RESOLVE) is 12
	// Mediterranean Forests, Woodlands & Scrub»
	function classText(c, lang) {
		var x;
		try {
			x = classCondition(c);
		} catch (err) {
			return JSON.stringify(c);
		}
		var names = x[1].map(function (v) { return categoryLabel(x[0], v, lang); });
		var or = lang === 'es' ? ' o ' : ' or ';
		var which = names.length > 1 ? names.slice(0, -1).join(', ') + or + names[names.length - 1] : names[0];
		if (lang === 'es') return x[0].index + ' (' + x[0].sensor + ') ' + (x[2] ? 'es' : 'no es') + ' ' + which;
		return x[0].index + ' (' + x[0].sensor + ') is ' + (x[2] ? '' : 'not ') + which;
	}

	// categorical.check_stats: an Error for a statistic over a region of the categorical entry E that is not one of
	// CLASS_STATS
	function checkClassStats(e, stats) {
		stats.forEach(function (s) {
			if (CLASS_STATS.indexOf(String(s).trim().toLowerCase()) < 0) {
				throw new Error(e.index + ' (' + e.sensor + ') is a categorical layer: its statistic over a region is the ' +
					'majority class (mode), not ' + s + '; for the area of each class, area_by_class');
			}
		});
	}

	// variable.class_conditions: [[entry, codes, keep]] of the conditions of S.where on a categorical layer
	function classConditions(s) {
		return (s.where || []).filter(function (c) {
			return !isLandcover(c) && isCategorical(byRef(c.ref));
		}).map(function (c) { return classCondition(c); });
	}

	// variable.pin_where: the conditions WHERE with the period START to END for those without a period of their own
	// (a land cover condition has its year)
	function pinWhere(where, start, end) {
		return (where || []).map(function (c) {
			var out = {};
			for (var k in c) out[k] = c[k];
			if (!out.period && start && !isLandcover(c)) out.period = [start, end];
			return out;
		});
	}

	// variable.where_specs: [[spec of its variable, min, max]] of each condition of S.where ({ref, min, max, and
	// optionally metric, temporal, interannual, quality, season, period}): the variable aggregated over the period of
	// S, or its own; the fixed layers have no period
	function whereSpecs(s) {
		return (s.where || []).filter(function (c) {
			if (isLandcover(c)) return false;
			var e = byRef(c.ref);
			if (isCategorical(e) || (c.classes !== undefined && c.classes !== null) ||
				(c.exclude !== undefined && c.exclude !== null)) {
				classCondition(c, e);  // checked (an error on a variable with values): see classConditions
				return false;
			}
			return true;
		}).map(function (c) {
			var e = byRef(c.ref);
			if ((c.min === null || c.min === undefined) && (c.max === null || c.max === undefined)) {
				throw new Error('the condition on ' + e.index + ' of where needs min, max or both');
			}
			var cs = {ref: c.ref, quality: c.quality || {}, temporal: c.temporal || 'period',
				interannual: c.interannual || 'mean', season: c.season !== undefined ? c.season : s.season};
			if (!e.static) {
				var period = c.period || s.period;
				if (!period) {
					throw new Error('the condition on ' + e.index + ' (' + e.sensor + ') needs a period: give it its own, ' +
						'or filter by other fixed layers (ELEVATION, SLOPE, TWI, the BIO variables of WorldClim)');
				}
				cs.period = period.slice();
				cs.metric = c.metric || e.metric || 'mean';
			}
			var label = 'where, the condition on ' + e.index + ' (' + e.sensor + '): ', outer = LABEL;
			LABEL = outer + label;  // its warnings, named as its errors: they are not about the result
			try {
				return [spec(cs), c.min, c.max];
			} catch (err) {  // e.g. a period without images of the variable of the condition (variable.where_specs)
				throw new Error(label + (err.message || String(err)));
			} finally {
				LABEL = outer;
			}
		});
	}

	// variable.mask: the image (1) of the pixels of S that pass its conditions (where, also those of land cover and
	// those on a categorical layer), masked elsewhere; null without conditions. A pixel where a condition has no data is
	// left out
	function whereMask(s, region, res) {
		// on the pixels RES of the result, by default those of its data (the package always computes a result on its
		// pixels): a condition on a fixed layer of bigger pixels (the TWI of 90 m under Sentinel-2) is then interpolated
		// as in the package, not taken from the nearest pixel of the layer
		res = res || (s.where && s.where.length ? Number(entryOf(s).m) : res);
		var masks = (s.where || []).filter(isLandcover).map(function (c) {
			return landcoverKeep(c, region, res);
		}).concat(classConditions(s).map(function (x) {
			return classKeep(x[0], x[1], x[2], res);
		})).concat(whereSpecs(s).map(function (w) {
			var value = image(w[0], region, res);
			var m = ee.Image(1).updateMask(value.mask());
			if (w[1] !== null && w[1] !== undefined) m = m.and(value.gte(Number(w[1])));
			if (w[2] !== null && w[2] !== undefined) m = m.and(value.lte(Number(w[2])));
			return m;
		}));
		if (!masks.length) return null;
		var out = masks[0];
		masks.slice(1).forEach(function (m) { out = out.and(m); });
		return out.selfMask();
	}

	// variable.check_rgb: error, without Earth Engine, if S has no true colour (see RGB): the data outside the catalog,
	// fixed layers, variables whose images have no red, green and blue bands, and the metrics that do not give colours
	// (see checkRgbMetric)
	function checkRgb(s) {
		var e = entryOf(s);
		if (e.custom) {
			throw new Error('only the variables of the catalog of MonitorEO have a true colour (of Sentinel-2, Landsat ' +
				'and the cloud frequency of MODIS)');
		}
		if (e.static) {
			throw new Error(e.index + ' (' + e.sensor + ') is a fixed layer, without dates: it has no images, nor true ' +
				'colour');
		}
		if (!rgbOf(e)) throw noRgb(e);
		checkRgbMetric(s.metric);
		if ((s.temporal || 'period') !== 'period') checkRgbMetric(s.interannual);
	}

	// variable.collection: the images of a variable of the catalog or of a collection of Earth Engine (fromCollection),
	// with the mask of the conditions of S (where) in every image, so the number of pixels and of images of each value
	// count only the pixels kept (with RGB, also the bands red, green and blue of their true colour: see
	// sensorCollection)
	function collection(s, region, res, rgb) {
		if (rgb) checkRgb(s);
		checkDates(s);
		var sp = span(s), e = entryOf(s);
		var col = e.custom ? fromCollection(e, region, sp[0], sp[1], res) :
			sensorCollection(e, region, sp[0], sp[1], s.quality, rgb);
		var m = whereMask(s, region, res);
		return m ? col.map(function (i) { return ee.Image(i).updateMask(m); }) : col;
	}

	// variable.image, for output pixels of RES metres (by default those of the data); with RGB, the true colour of its
	// images instead (bands red, green and blue: surface reflectance), on the same pixels and with the same metric
	function image(s, region, res, rgb) {
		if (rgb) {
			checkRgb(s);
			var col = collection(s, region, res, true);
			return composite(col, s.metric, s.temporal, s.interannual, s.period, s.season, ['value'].concat(RGB_BANDS))
				.select(RGB_BANDS);
		}
		if (isStatic(s)) {  // a categorical layer: its polygons rasterized (never interpolated), before staticImage
			var img = isCategorical(entryOf(s)) ? categoricalImage(entryOf(s), res) : staticImage(entryOf(s), res);
			var m = whereMask(s, region, res);
			return m ? img.updateMask(m) : img;
		}
		return composite(collection(s, region, res), s.metric, s.temporal, s.interannual, s.period, s.season);
	}

	// Regions (areas.py) --------------------------------------------------------------------------------------------

	var ECOREGIONS = 'RESOLVE/ECOREGIONS/2017';
	var WDPA = 'WCMC/WDPA/current/polygons';
	var WDPA_FIELDS = ['SITE_ID', 'NAME', 'NAME_ENG', 'DESIG', 'DESIG_ENG', 'DESIG_TYPE', 'IUCN_CAT', 'ISO3', 'REP_AREA',
		'STATUS_YR'];
	var RAMSAR = 'Ramsar Site';  // in DESIG_ENG: «Wetland of International Importance (Ramsar Site)»
	var GAUL = {1: 'FAO/GAUL/2025/level1', 2: 'FAO/GAUL/2025/level2'};  // areas.GAUL
	var GAUL_FIELDS = {1: ['GAUL0_NAME', 'GAUL1_CODE', 'GAUL1_NAME', 'ISO3_CODE', 'DISP_EN'],
		2: ['GAUL0_NAME', 'GAUL1_NAME', 'GAUL2_CODE', 'GAUL2_NAME', 'ISO3_CODE', 'DISP_EN']};
	// municipalities.ASSET: the municipalities of Spain (the administrative units of level 3, of the Instituto
	// Geográfico Nacional), a public table with code (of the INE, 5 digits), name, province, region, national_code and
	// search (the name as municipalityPlain gives it)
	var MUNICIPALITIES = 'projects/ee-ugr-default-project/assets/monitoreo/municipalities_es';
	var MUNICIPALITY_FIELDS = ['code', 'name', 'province', 'region'];
	// the table of each level of the administrative units: FAO GAUL 2025 (1 and 2) and the municipalities of Spain (3)
	var ADMIN_DATASETS = {1: GAUL[1], 2: GAUL[2], 3: MUNICIPALITIES};
	var ISLANDS = 'projects/sat-io/open-datasets/shoreline/big_islands';  // areas.ISLANDS
	// seas.ASSET: the oceans and seas (the sea areas of the IHO, of Marine Regions), a public table with mrgid, name,
	// area_km2 and search (the name as seaPlain gives it)
	var SEAS = 'projects/ee-ugr-default-project/assets/monitoreo/seas_iho';
	var SEA_FIELDS = ['mrgid', 'name', 'area_km2'];
	// the tables of the regions whose credits and references the app shows under the region (adminCredits): the
	// administrative units by their level and the seas
	var CITED_REGIONS = {1: GAUL[1], 2: GAUL[2], 3: MUNICIPALITIES, sea: SEAS};
	// areas.LARGE_AREA_KM2, LARGE_PIXEL and NICE_SCALES: the large areas (more than 100,000 km²) are computed by
	// default on pixels of 1 to 10 km (defaultScale)
	var LARGE_AREA_KM2 = 100000;
	var LARGE_PIXEL = [1000, 10000];
	var NICE_SCALES = [];
	for (var ne = 1; ne < 6; ne++) [1, 2, 5].forEach(function (m) { NICE_SCALES.push(m * Math.pow(10, ne)); });
	var WDPA_MAX_ERROR = 10;
	var BIOME_MAX_ERROR = 100;  // areas.BIOME_MAX_ERROR: metres, the tolerance of the union of a biome's ecoregions
	var BIOME_CODES = '1 to 14 or 99 (Rock and Ice)';  // areas.BIOME_CODES: the codes of the biomes, in the messages
	var WITHIN_MAX_ERROR = 100;  // areas.WITHIN_MAX_ERROR: metres, the union of the region of within, the part inside
	// areas.GLOBAL_CRS and WIDE_DEGREES: the CRS (equal area, metres) of the regions whose bounds span more degrees of
	// longitude than that (or cross the antimeridian), too wide for a UTM zone
	var GLOBAL_CRS = 'EPSG:6933';
	var WIDE_DEGREES = 40;
	// areas.PACIFIC_CRS: the span of a region across the antimeridian (360 in EPSG:4326) is that of its bounds in a
	// Mercator centred on the Pacific, PACIFIC_M_PER_DEGREE metres of x per degree
	var PACIFIC_CRS = 'EPSG:3832';
	var PACIFIC_M_PER_DEGREE = 6378137 * 3.141592653589793 / 180;

	// areas.utm_of
	function utmOf(lon, lat) {
		var zone = Math.min(Math.floor((lon + 180) / 6) + 1, 60);
		return 'EPSG:' + ((lat >= 0 ? 32600 : 32700) + zone);
	}

	// areas.crs_for: the automatic CRS of a region from INFO (regionInfo: its centroid, the coordinates of its bounds
	// and, across the antimeridian, those of its bounds in PACIFIC_CRS): GLOBAL_CRS when it spans more than
	// WIDE_DEGREES of longitude (360 across the antimeridian without pacific), else the UTM zone of the centre (also
	// without bounds)
	function regionCrs(info) {
		var ring = (info.bounds || [[]])[0];
		var lons = ring.map(function (p) { return p[0]; });
		var span = lons.length ? Math.max.apply(null, lons) - Math.min.apply(null, lons) : 0;
		if (span > 359 && info.pacific) {  // across the antimeridian: its real span, in the Mercator of the Pacific
			var xs = info.pacific[0].map(function (p) { return p[0]; });
			span = (Math.max.apply(null, xs) - Math.min.apply(null, xs)) / PACIFIC_M_PER_DEGREE;
		}
		if (span > WIDE_DEGREES) return GLOBAL_CRS;
		return utmOf(info.centroid[0], info.centroid[1]);
	}

	function named(fc, field) {
		return fc.map(function (f) { return f.set('name', ee.String(f.get(field))); });
	}

	// The case variants of a text searched (areas._variants)
	function variantsOf(text) {
		var t = String(text).trim();
		var title = t.toLowerCase().replace(/(^|[^A-Za-zÀ-ÿ])([a-zà-ÿ])/g, function (m, a, b) {
			return a + b.toUpperCase();
		});
		return [t, title, t.toUpperCase(), t.toLowerCase(), t.charAt(0).toUpperCase() + t.slice(1).toLowerCase()]
			.filter(function (v, i, a) { return a.indexOf(v) === i; }).sort();
	}

	// areas.find_admin_units: ee.FeatureCollection (without geometries) of the administrative units of FAO GAUL 2025
	// of LEVEL (1 or 2) whose name contains TEXT, in COUNTRY (ISO3) if given
	function findAdminUnits(text, level, country, limit) {
		var f = ee.Filter.or.apply(null, variantsOf(text).map(function (v) {
			return ee.Filter.stringContains('GAUL' + level + '_NAME', v);
		}));
		if (country) f = ee.Filter.and(f, ee.Filter.eq('ISO3_CODE', String(country).trim().toUpperCase()));
		return ee.FeatureCollection(GAUL[level]).filter(f).limit(limit || 20).map(function (x) {
			return ee.Feature(null, x.toDictionary(GAUL_FIELDS[level])).set('level', level);
		});
	}

	// areas.region of {admin1: CODE} or {admin2: CODE}: the unit, named by its full name (DISP_EN); of LEVEL 3, the
	// municipalities of Spain {admin3: CODE} (municipalityRegion)
	function adminRegion(level, code) {
		if (Number(level) === 3) return municipalityRegion(code);
		return named(ee.FeatureCollection(GAUL[level]).filter(ee.Filter.eq('GAUL' + level + '_CODE', code)), 'DISP_EN');
	}

	// municipalities._plain: TEXT in lower case, without accents (its NFKD, only the ASCII), with its apostrophes as
	// "'" (municipalities.APOSTROPHES: U+2019, U+2018, U+02BC and U+00B4, else "L'Hospitalet" typed with U+2019 would
	// be "lhospitalet"), and the separators of the bilingual names ('/', '-') as spaces, its words separated by one
	// space: the property search of the table of the municipalities (MUNICIPALITIES), so that they are found on the
	// server whatever the case and accents
	function municipalityPlain(text) {
		var s = String(text === null || text === undefined ? '' : text).replace(/[\u2019\u2018\u02bc\u00b4]/g, "'")
			.normalize('NFKD').replace(/[^\x00-\x7f]/g, '');
		return s.toLowerCase().replace(/[\/\-]/g, ' ').split(/[\s\x1c-\x1f]+/).filter(Boolean).join(' ');
	}

	// areas.find_admin_units of level 3 (municipalities.find): ee.FeatureCollection (without geometries) of the
	// municipalities of Spain whose name contains TEXT (any case and accents: their property search) or whose code of the
	// INE begins with it, at most LIMIT: the very name first, then those that begin with it, then the others, each by
	// name and code; with their code, name, province, region and level 3
	function findMunicipalities(text, limit) {
		var t = municipalityPlain(text);
		var f = ee.Filter.or(ee.Filter.stringContains('search', t), ee.Filter.stringStartsWith('code', t));
		return ee.FeatureCollection(MUNICIPALITIES).filter(f).map(function (x) {
			var s = ee.String(x.get('search'));
			var rank = ee.Algorithms.If(s.equals(t), '0', ee.Algorithms.If(s.index(t).eq(0), '1', '2'));
			return ee.Feature(null, x.toDictionary(MUNICIPALITY_FIELDS)).set('level', 3)
				.set('order', ee.String(rank).cat(s).cat(' ').cat(x.get('code')));
		}).sort('order').limit(limit || 20);
	}

	// areas.municipality_codes, without the index of the package (the app has not got it, and finds them in the table):
	// V (the code of the INE of a municipality of Spain, or a list of them; '18134' or 18134) as codes of 5 digits (with
	// the zeros on the left, as str.zfill); an Error if one is not 5 digits, or if there are none
	function municipalityCodes(v) {
		var codes = (Array.isArray(v) ? v : [v]).map(function (x) {
			var s = String(x).trim(), sign = s.charAt(0) === '-' || s.charAt(0) === '+' ? s.charAt(0) : '';
			s = s.slice(sign.length);
			while (sign.length + s.length < 5) s = '0' + s;
			return sign + s;
		});
		var bad = codes.filter(function (c) { return !/^[0-9]{5}$/.test(c); });
		if (!codes.length || bad.length) {
			throw new Error("admin3 is the code of the INE of a municipality of Spain (5 digits, e.g. '18134'): " +
				(bad.join(', ') || 'none given') + ' is not one (find them with find_admin_units, level 3)');
		}
		return codes;
	}

	// areas.region of {admin3: V}: the municipalities of Spain of the codes V (municipalityCodes), each named
	// 'name (province)'
	function municipalityRegion(v) {
		var codes = municipalityCodes(v);
		var fc = ee.FeatureCollection(MUNICIPALITIES).filter(ee.Filter.inList('code', codes));
		return fc.map(function (f) {
			return f.set('name', ee.String(f.get('name')).cat(' (').cat(f.get('province')).cat(')'));
		});
	}

	// references._region and of_datasets for the administrative units of LEVEL (FAO GAUL 2025, 1 and 2; the
	// municipalities of Spain of the IGN, 3): {credits: the lines that the terms of use of its data ask for, references:
	// [{citation, url, text}]}, as catalog.json gives them (build.py writes them into catalog.js, regions)
	function adminCredits(level) {
		var d = (CATALOG.regions || {})[CITED_REGIONS[level]] || {};
		return {credits: d.credit ? [d.credit] : [], references: d.references || []};
	}

	// seas.plain: TEXT in lower case, without accents (its NFKD, only the ASCII), its apostrophes as "'" and every
	// other sign that is not a letter, a digit or "'" as a space, its words separated by one space ('Balearic (Iberian
	// Sea)' is 'balearic iberian sea'): the property search of the table of the seas (SEAS)
	function seaPlain(text) {
		var s = String(text === null || text === undefined ? '' : text).replace(/[\u2019\u2018\u02bc\u00b4]/g, "'")
			.normalize('NFKD').replace(/[^\x00-\x7f]/g, '');
		return s.toLowerCase().replace(/[^a-z0-9']+/g, ' ').split(' ').filter(Boolean).join(' ');
	}

	// areas.find_seas (seas.find): ee.FeatureCollection (without geometries) of the seas whose name contains TEXT (any
	// case and accents: their property search) or whose MRGID is TEXT, at most LIMIT: the very name first, then those
	// that begin with it, then the others, each by name; with their mrgid, name and area_km2
	function findSeas(text, limit) {
		var t = seaPlain(text);
		var f = /^[0-9]+$/.test(t) ? ee.Filter.or(ee.Filter.stringContains('search', t), ee.Filter.eq('mrgid', Number(t))) :
			ee.Filter.stringContains('search', t);
		return ee.FeatureCollection(SEAS).filter(f).map(function (x) {
			var s = ee.String(x.get('search'));
			var rank = ee.Algorithms.If(s.equals(t), '0', ee.Algorithms.If(s.index(t).eq(0), '1', '2'));
			return ee.Feature(null, x.toDictionary(SEA_FIELDS)).set('order', ee.String(rank).cat(s));
		}).sort('order').limit(limit || 20);
	}

	// seas.codes, without the index of the package (the app has not got it, and finds the seas in the table): V (the
	// MRGID of a sea or its name, or a list of them) as {mrgids: [numbers], names: [names as seaPlain gives them]}; an
	// Error if there are none
	function seaCodes(v) {
		var values = Array.isArray(v) ? v : [v], out = {mrgids: [], names: []};
		values.forEach(function (x) {
			var s = String(x === null || x === undefined ? '' : x).trim();
			if (/^[0-9]+(\.0*)?$/.test(s)) out.mrgids.push(Number(s));
			else if (seaPlain(s)) out.names.push(seaPlain(s));
		});
		if (!out.mrgids.length && !out.names.length) {
			throw new Error("sea is the MRGID of a sea area of the IHO (e.g. 3324) or its name (e.g. 'Alboran Sea'): " +
				(values.join(', ') || 'none given') + ' is not one (find them with find_seas)');
		}
		return out;
	}

	// areas.region of {sea: V}: the seas of the MRGIDs or names V (seaCodes), each named by its name
	function seaRegion(v) {
		var c = seaCodes(v), fc = ee.FeatureCollection(SEAS), filters = [];
		if (c.mrgids.length) filters.push(ee.Filter.inList('mrgid', c.mrgids));
		if (c.names.length) filters.push(ee.Filter.inList('search', c.names));
		return fc.filter(filters.length > 1 ? ee.Filter.or(filters[0], filters[1]) : filters[0]);
	}

	// areas.region of {sea_at: [LON, LAT]}: the sea area of the IHO at that point (none on land)
	function seaAt(lon, lat) {
		return ee.FeatureCollection(SEAS).filterBounds(ee.Geometry.Point([lon, lat]));
	}

	// areas.is_sea: whether the region of the parameters SPEC is a sea (sea or sea_at) or within one
	function isSea(spec) {
		if (!spec || typeof spec !== 'object') return false;
		return (spec.sea !== null && spec.sea !== undefined) || (spec.sea_at !== null && spec.sea_at !== undefined) ||
			isSea(spec.within);
	}

	// services.sea_warning: the warning of a variable of the catalog ENTRY without data over the open sea (without sea)
	// computed over a sea (the region of the parameters SPEC, see isSea), or null
	function seaWarning(spec, entry) {
		if (!isSea(spec) || !entry || entry.custom || entry.sea) return null;
		var marine = CATALOG.variables.filter(function (e) { return e.sea; })
			.map(function (e) { return e.index + ' (' + e.sensor + ')'; });
		marine = marine.filter(function (m, i) { return marine.indexOf(m) === i; }).sort();
		return entry.index + ' of ' + entry.sensor + ' has no data over the open sea: its data are of the land ' +
			'(Sentinel-2 and Landsat see the coastal waters only). Over a sea, use ' + marine.join(', ') + '.';
	}

	// areas.region of {island_at: [LON, LAT]}: the island of more than 1 km² at that point
	function islandAt(lon, lat) {
		var label = 'Island at ' + lat.toFixed(5) + ', ' + lon.toFixed(5);
		return ee.FeatureCollection(ISLANDS).filterBounds(ee.Geometry.Point([lon, lat])).map(function (f) {
			return f.set('name', ee.Algorithms.If(ee.String(f.get('Name')).length().gt(0), f.get('Name'), label));
		});
	}

	// areas.find_protected_areas: ee.FeatureCollection (without geometries) of the protected areas whose name
	// contains TEXT; with RAMSAR, only the Ramsar sites
	function findProtectedAreas(text, limit, ramsar) {
		var t = String(text).trim();
		var title = t.toLowerCase().replace(/(^|[^A-Za-zÀ-ÿ])([a-zà-ÿ])/g, function (m, a, b) {
			return a + b.toUpperCase();
		});
		var variants = [t, title, t.toUpperCase(), t.toLowerCase(), t.charAt(0).toUpperCase() + t.slice(1).toLowerCase()]
			.filter(function (v, i, a) { return a.indexOf(v) === i; }).sort();
		var f = [];
		variants.forEach(function (v) { f.push(ee.Filter.stringContains('NAME', v)); });
		variants.forEach(function (v) { f.push(ee.Filter.stringContains('NAME_ENG', v)); });
		var filter = ee.Filter.or.apply(null, f);
		if (ramsar) filter = ee.Filter.and(filter, ee.Filter.stringContains('DESIG_ENG', RAMSAR));
		return ee.FeatureCollection(WDPA).filter(filter).limit(limit || 20).map(function (x) {
			return ee.Feature(null, x.toDictionary(WDPA_FIELDS));
		});
	}

	// The simplified geometries of the protected areas IDS (areas._fetched), to evaluate once: then wdpaRegion
	function wdpaGeometries(ids) {
		var f = ee.Filter.or(ee.Filter.inList('SITE_ID', ids), ee.Filter.inList('WDPAID', ids));
		return named(ee.FeatureCollection(WDPA).filter(f), 'NAME').map(function (x) {
			return ee.Feature(x.geometry(), {name: x.get('name')}).simplify(WDPA_MAX_ERROR);
		});
	}

	// areas._geojson_polygons: the polygons of a GeoJSON geometry (WDPA has collections with lines), or null
	function geojsonPolygons(geom) {
		if (geom.type === 'Polygon' || geom.type === 'MultiPolygon') return geom;
		if (geom.type !== 'GeometryCollection') return null;
		var coords = [];
		(geom.geometries || []).forEach(function (g) {
			if (g.type === 'Polygon') coords.push(g.coordinates);
			else if (g.type === 'MultiPolygon') coords = coords.concat(g.coordinates);
		});
		return coords.length ? {type: 'MultiPolygon', coordinates: coords} : null;
	}

	// ee.FeatureCollection of the evaluated wdpaGeometries
	function wdpaRegion(info) {
		var feats = [];
		info.features.forEach(function (f) {
			var g = geojsonPolygons(f.geometry);
			if (g) feats.push(ee.Feature(ee.Geometry(g), {name: f.properties.name}));
		});
		if (!feats.length) throw new Error('no protected area of WDPA with that ID');
		return ee.FeatureCollection(feats);
	}

	function ecoregionAt(lon, lat) {
		return named(ee.FeatureCollection(ECOREGIONS).filterBounds(ee.Geometry.Point([lon, lat])), 'ECO_NAME');
	}

	// areas._whole: X as a whole number, or null if it is not one
	function wholeNumber(x) {
		var text = String(x).trim(), f = Number(text);
		return text !== '' && isFinite(f) && f === Math.round(f) ? f : null;
	}

	// catalog.biomes: the biomes of RESOLVE Ecoregions 2017 (the classes of BIOME), [{code, name (in Spanish with LANG
	// 'es'), colour}], from the lowest code
	function biomes(lang) {
		var rows = classRows('biomes');
		return Object.keys(rows).map(Number).sort(function (a, b) { return a - b; }).map(function (code) {
			var row = rows[code];
			return {code: code, name: (lang === 'es' && row.name_es) || row.name, colour: row.colour};
		});
	}

	// areas.biome_name: the name of the biome CODE (in Spanish with LANG 'es'), or null
	function biomeName(code, lang) {
		var c = wholeNumber(code), b = biomes(lang).filter(function (x) { return x.code === c; })[0];
		return b ? b.name : null;
	}

	// catalog.ecoregions_of_biome: the ECO_IDs of the ecoregions of the biome CODE in the table of classes (99, Rock
	// and Ice, is the ECO_ID 0), from the lowest
	function ecoregionsOfBiome(code) {
		var rows = classRows('ecoregions');
		return Object.keys(rows).map(Number).filter(function (eco) { return Number(rows[eco].group) === Number(code); })
			.sort(function (a, b) { return a - b; });
	}

	// areas.biome_codes: V (a code of a biome, a list of them or a text with commas) as the codes of the biomes, each
	// once, in their order; an Error if one is not a code of the table of the biomes, or if there are none
	function biomeCodes(v) {
		var values = typeof v === 'string' ? v.replace(/;/g, ',').split(',').filter(function (x) { return x.trim(); }) :
			Array.isArray(v) ? v : [v];
		if (!values.length) {
			throw new Error('biome_id takes the codes of the biomes of RESOLVE Ecoregions 2017, ' + BIOME_CODES +
				', e.g. 12: list_classes of BIOME gives them');
		}
		var known = biomes().map(function (b) { return b.code; }), out = [];
		values.forEach(function (x) {
			var c = wholeNumber(x);
			if (c === null || known.indexOf(c) < 0) {
				var shown = c !== null ? String(c) : typeof x === 'string' ? repr(x) : String(x);
				throw new Error('biome_id takes the codes of the biomes of RESOLVE Ecoregions 2017, ' + BIOME_CODES +
					', not ' + shown + ': list_classes of BIOME gives them');
			}
			if (out.indexOf(c) < 0) out.push(c);
		});
		return out;
	}

	// areas._biome: the biome CODE as a single feature named by its name (and with its code, biome): the union of the
	// ecoregions of its ECO_IDs in the table of classes, dissolved with a tolerance of BIOME_MAX_ERROR m; with INSIDE
	// (an ee.Geometry), only the ecoregions that touch it
	function biomeFeature(code, inside) {
		var eco = ee.FeatureCollection(ECOREGIONS).filter(ee.Filter.inList('ECO_ID', ecoregionsOfBiome(code)));
		if (inside) eco = eco.filterBounds(inside);
		var union = eco.geometry(BIOME_MAX_ERROR).dissolve(BIOME_MAX_ERROR);
		return ee.Feature(union, {name: biomeName(code), biome: code});
	}

	// areas.region of {biome_id: V}: a feature per biome of V (see biomeCodes), only their ecoregions that touch INSIDE
	// if given (then withinRegion keeps their part inside it)
	function biomeRegion(v, inside) {
		return ee.FeatureCollection(biomeCodes(v).map(function (c) { return biomeFeature(c, inside); }));
	}

	// areas._biome_at, the region {biome_at: [LON, LAT]}: the biome of the ecoregion at the point as biomeFeature
	// (two at a boundary; none in the sea); of each biome, its feature if one of its ecoregions is there (If: only that
	// one is joined)
	function biomeAt(lon, lat, inside) {
		var at = ee.FeatureCollection(ECOREGIONS).filterBounds(ee.Geometry.Point([lon, lat]));
		var feats = biomes().map(function (b) {
			return ee.Algorithms.If(at.filter(ee.Filter.inList('ECO_ID', ecoregionsOfBiome(b.code))).size(),
				biomeFeature(b.code, inside), null);
		});
		return ee.FeatureCollection(ee.List(feats).removeAll([null]));
	}

	// areas._within: the part of each feature of FC inside INSIDE (the geometry of the region of within, with the
	// tolerance WITHIN_MAX_ERROR: e.g. bboxRegion(bounds).geometry(WITHIN_MAX_ERROR)), with its properties; the
	// features outside it are left out
	function withinRegion(fc, inside) {
		return fc.filterBounds(inside).map(function (f) {
			return f.intersection(ee.Feature(inside), WITHIN_MAX_ERROR);
		});
	}

	function bboxRegion(bbox, name) {
		return ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle(bbox, null, false), {name: name || 'bbox'})]);
	}

	// Time series (timeseries.py) -----------------------------------------------------------------------------------

	var STEPS = ['daily', '16-day', 'monthly', 'annual'];
	var MAX_ROWS = 4000;
	var MAX_STEPS = 120;
	var TARGET_PIXELS = 1e6;
	var SPLIT_ERRORS = ['too many concurrent', 'memory limit', 'timed out', 'computation timed out'];
	var RETRY_ERRORS = ['429', 'quota', 'unavailable', '503', '500', 'deadline', 'internal error'];

	// The steps of timeseries.bins, except 'daily' (dailyDays)
	function seriesBins(s, step) {
		var wins = windows(s.period, s.season);
		var out = [];
		if (step === 'annual') {
			wins.forEach(function (w) { out.push([w[1], w[2]]); });
		} else if (step === 'monthly' || step === '16-day') {
			wins.forEach(function (w) {
				bins(w, step).forEach(function (b) { out.push([b[1], b[2]]); });
			});
		} else {
			throw new Error('unknown step ' + step + ': use ' + STEPS.join(', '));
		}
		return out.map(function (b) { return [iso(b[0]), iso(b[1])]; });
	}

	// Animations (services.timelapse, monitoreo.animation): a frame per step of the period, the metric of its images
	// coloured with one colour ramp for every frame, on a light grey region (no data) over white, with its outline. The
	// app shows them as a ui.Thumbnail of the frames; the dates go in a label (the GIF of Python has them written)
	var ANIMATION_STEPS = ['annual', 'monthly', '16-day'];  // the days with images (daily) only in Python
	var MAX_FRAMES = 120;
	var TOTALS = ['sum', 'count', 'days'];  // metrics that grow with the images or the days: that of the period is that
	// of all its steps
	var FRAME_COLOURS = {noData: 'd9d9d9', outside: 'ffffff', outline: '000000'};
	var MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
		'October', 'November', 'December'];
	var MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
		'noviembre', 'diciembre'];

	// animation.label: the date of a frame of STEP from FIRST to the day before AFTER
	function frameLabel(step, first, after, lang) {
		var a = date(first), last = addDays(date(after), -1);
		if (step === 'annual') {
			return a.getUTCFullYear() === last.getUTCFullYear() ? String(a.getUTCFullYear()) :
				a.getUTCFullYear() + '-' + last.getUTCFullYear();
		}
		if (step === 'monthly') {
			return (lang === 'es' ? MESES : MONTH_NAMES)[a.getUTCMonth()] + (lang === 'es' ? ' de ' : ' ') +
				a.getUTCFullYear();
		}
		return iso(a) === iso(last) ? iso(a) : iso(a) + (lang === 'es' ? ' a ' : ' to ') + iso(last);
	}

	// The steps of the frames of S ([first day, day after the last]), at most MAX_FRAMES (animation.check)
	function animationSteps(s, step) {
		if (ANIMATION_STEPS.indexOf(step) < 0) {
			throw new Error('unknown step ' + step + ': use ' + ANIMATION_STEPS.join(', '));
		}
		var steps = seriesBins(s, step);
		if (steps.length > MAX_FRAMES) {
			throw new Error(steps.length + ' frames: an animation has at most ' + MAX_FRAMES + '; use a longer step ' +
				'(annual, monthly) or a shorter period');
		}
		if (!steps.length) throw new Error('the period (and season) has no time step');
		return steps;
	}

	// ee.ImageCollection of the frames (animation.frames) of the variable S over REGIONS, a frame per STEPS, each the
	// METRIC of its images coloured with VIS
	function animationFrames(s, regions, steps, metric, vis) {
		var col = collection(s, regions.geometry());
		var outside = ee.Image.constant(0).visualize({palette: [FRAME_COLOURS.outside]});
		var inside = ee.Image.constant(0).clipToCollection(regions).visualize({palette: [FRAME_COLOURS.noData]});
		var outline = ee.Image().byte().paint(regions, 1, 2).visualize({palette: [FRAME_COLOURS.outline]});
		return ee.ImageCollection.fromImages(steps.map(function (b) {
			var value = reduceSpan(col, metric, b[0], b[1]).clipToCollection(regions);
			return outside.blend(inside).blend(value.visualize(vis)).blend(outline)
				.set('system:time_start', date(b[0]).getTime());
		}));
	}

	// Area by class (services.area_by_class, monitoreo.classes): hectares and % of each class over each feature, of a
	// land cover map of a year, of the map of a variable cut at some values (breaks) or of its trend on each pixel
	var TREND_CLASSES = [[-1, 'significant decrease', 'd7191c', 'disminución significativa'],
		[0, 'no significant trend', 'bdbdbd', 'sin tendencia significativa'],
		[1, 'significant increase', '1a9641', 'aumento significativo']];
	var LANDCOVER_COLOURS = {water: '419bdf', trees: '397d49', grassland: '88b053', wetland: '7a87c6',
		cropland: 'e49635', shrubland: 'dfc35a', built: 'c4281b', bare: 'a59b8f', snow: 'b39fe1'};
	var AREA_TARGET_PIXELS = 1e7;

	// classes.check_breaks: an increasing list of numbers, from a list or a text with commas
	function checkBreaks(breaks) {
		if (typeof breaks === 'string') breaks = breaks.replace(/;/g, ',').split(',').filter(function (b) { return b.trim(); });
		var out = (breaks || []).map(function (b) { return Number(b); });
		if (!out.length) throw new Error('give at least one break, e.g. [0.2, 0.4, 0.6]');
		if (out.some(function (b) { return !isFinite(b); })) {
			throw new Error('breaks are numbers, e.g. [0.2, 0.4, 0.6]; not ' + JSON.stringify(breaks));
		}
		for (var i = 1; i < out.length; i++) {
			if (out[i] <= out[i - 1]) throw new Error('breaks go from the lowest to the highest, each once: ' + out.join(', '));
		}
		return out;
	}

	function brk(x) {
		return String(Number(x.toPrecision(6)));
	}

	// classes.break_classes: [class, label, from, to] of the classes of BREAKS, the labels with UNIT
	function breakClasses(breaks, unit, lang) {
		var u = unit ? ' ' + unit : '', es = lang === 'es';
		var out = [[0, (es ? 'menos de ' : 'below ') + brk(breaks[0]) + u, null, breaks[0]]];
		for (var i = 1; i < breaks.length; i++) {
			out.push([i, brk(breaks[i - 1]) + (es ? ' a ' : ' to ') + brk(breaks[i]) + u, breaks[i - 1], breaks[i]]);
		}
		out.push([breaks.length, brk(breaks[breaks.length - 1]) + u + (es ? ' o más' : ' or more'),
			breaks[breaks.length - 1], null]);
		return out;
	}

	// classes.classify_breaks
	function classifyBreaks(value, breaks) {
		var out = ee.Image.constant(0).updateMask(ee.Image(value).mask().select(0));
		breaks.forEach(function (b) { out = out.add(ee.Image(value).gte(b)); });
		return out.toInt().rename('class');
	}

	// classes.classify_trend: -1 significant decrease, 0 no significant trend, 1 significant increase
	function classifyTrend(trend, alpha) {
		trend = ee.Image(trend);
		var slope = trend.select('slope');
		return trend.select('p_value').lt(alpha || 0.05).multiply(slope.gt(0).subtract(slope.lt(0))).toInt()
			.rename('class').updateMask(slope.mask());
	}

	// classes.scale_for, from the AREA of the biggest region (m²)
	function areaScale(native, area) {
		return defaultScale(native, area, AREA_TARGET_PIXELS);
	}

	// classes.hectares: the grouped sum of the true area of the pixels by class over each feature, to evaluate
	function classHectares(classesImg, regions, scale, crs) {
		return ee.Image.pixelArea().divide(1e4).updateMask(ee.Image(classesImg).mask()).addBands(classesImg)
			.reduceRegions({collection: regions, reducer: ee.Reducer.sum().group(1, 'class'), scale: scale, crs: crs,
				tileScale: 4});
	}

	// classes.rows: [{region, class, label, ..., ha, percent}] of the evaluated FEATURES of classHectares, for CLASSES
	// ([class, label, {more columns}]) and the columns of EXTRA
	function areaRows(features, classes, extra) {
		var out = [];
		features.forEach(function (f) {
			var ha = {};
			(f.properties.groups || []).forEach(function (g) { ha[Math.round(g['class'])] = g.sum; });
			var total = classes.reduce(function (a, c) { return a + (ha[c[0]] || 0); }, 0);
			classes.forEach(function (c) {
				var row = {region: String(f.properties.name)};
				Object.keys(extra || {}).forEach(function (k) { row[k] = extra[k]; });
				row['class'] = c[0];
				row.label = c[1];
				Object.keys(c[2] || {}).forEach(function (k) { row[k] = c[2][k]; });
				row.ha = ha[c[0]] || 0;
				row.percent = total ? 100 * row.ha / total : null;
				out.push(row);
			});
		});
		return out;
	}

	// Gradients (services.region_stats with zones, services.transect): the statistics of a map in each band of another
	// variable, and its profile along a line with the elevation
	var ZONE_STATS = ['p25', 'p50', 'p75', 'mean'];

	// The grouped statistics (ZONE_STATS and the count) of the image VALUE in each zone of ZONE over each feature, to
	// evaluate
	function zoneStats(value, zone, regions, scale, crs) {
		var red = ee.Reducer.percentile([25, 50, 75]).combine(ee.Reducer.mean(), '', true)
			.combine(ee.Reducer.count(), '', true);
		return ee.Image(value).rename('value').addBands(zone).reduceRegions({collection: regions,
			reducer: red.group(1, 'zone'), scale: scale, crs: crs, tileScale: 4});
	}

	// The rows of the evaluated FEATURES of zoneStats for the zones of LEGEND (breakClasses)
	function zoneRows(features, legend) {
		var out = [];
		features.forEach(function (f) {
			var by = {};
			(f.properties.groups || []).forEach(function (g) { by[Math.round(g.zone)] = g; });
			legend.forEach(function (z) {
				var g = by[z[0]] || {};
				var row = {region: String(f.properties.name), zone: z[0], zone_label: z[1], zone_from: z[2], zone_to: z[3]};
				ZONE_STATS.forEach(function (s) { row[s] = g[s] === undefined ? null : g[s]; });
				row.n_pixels = g.count || 0;
				out.push(row);
			});
		});
		return out;
	}

	// services._class_zone: the image of the zones of the categorical layer ZS (a spec; band 'zone': the code of the
	// class of each pixel), only of the classes CODES if given
	function classZone(zs, region, scale, codes) {
		var zone = image(zs, region, scale);
		if (codes && codes.length) zone = zone.remap(codes, codes);
		return zone.rename('zone');
	}

	// services.region_stats with the zones of the categorical entry ZE: the rows of the zones with pixels of the
	// evaluated FEATURES of zoneStats (zone: the code of the class; zone_label: its code and name, in LANG)
	function classZoneRows(features, ze, lang) {
		var out = [];
		features.forEach(function (f) {
			(f.properties.groups || []).slice().sort(function (a, b) { return a.zone - b.zone; }).forEach(function (g) {
				var z = Math.round(g.zone);
				var row = {region: String(f.properties.name), zone: z, zone_label: categoryLabel(ze, z, lang), zone_from: null,
					zone_to: null};
				ZONE_STATS.forEach(function (s) { row[s] = g[s] === undefined ? null : g[s]; });
				row.n_pixels = g.count || 0;
				out.push(row);
			});
		});
		return out;
	}

	// services.area_by_class of the categorical entry E: the legend ([class, label, {group, group_label}]: the
	// ecoregions with their biome) of the classes with area in some evaluated feature of classHectares, in LANG
	function classAreaLegend(e, features, lang) {
		var present = [];
		features.forEach(function (f) {
			(f.properties.groups || []).forEach(function (g) {
				if (g.sum) present.push(Math.round(g['class']));
			});
		});
		var group = categoryGroupEntry(e);
		return uniqueSorted(present).map(function (c) {
			var more = {};
			if (group) {
				more.group = categoryGroupOf(e, c);
				more.group_label = categoryLabel(group, more.group, lang);
			}
			return [c, categoryLabel(e, c, lang), more];
		});
	}

	// classes.by_group: the hectares of the classes of LEGEND (classAreaLegend) in each evaluated feature of
	// classHectares summed by group (the biome of each ecoregion; GROUP, its entry): [{region, group, label, ha,
	// percent}], only those with area
	function classGroupRows(features, legend, group, lang) {
		var out = [];
		features.forEach(function (f) {
			var ha = {};
			(f.properties.groups || []).forEach(function (g) { ha[Math.round(g['class'])] = g.sum; });
			var total = legend.reduce(function (a, c) { return a + (ha[c[0]] || 0); }, 0);
			var acc = {};
			legend.forEach(function (c) {
				if (ha[c[0]]) acc[c[2].group] = (acc[c[2].group] || 0) + ha[c[0]];
			});
			uniqueSorted(Object.keys(acc)).forEach(function (g) {
				out.push({region: String(f.properties.name), group: g, label: categoryLabel(group, g, lang), ha: acc[g],
					percent: total ? 100 * acc[g] / total : null});
			});
		});
		return out;
	}

	// services.transect: the distances where the line of LENGTH metres is cut every STEP metres, none within a
	// millionth of a step of its end (with STEP = LENGTH / N, N × STEP may fall a hair short of LENGTH)
	function transectCuts(length, step) {
		var out = [];
		for (var i = 1; i * step < length - step * 1e-6; i++) out.push(i * step);
		return out;
	}

	// The mean of VALUE and of the elevation DEM over each segment of LINE cut at CUTS (each within half a pixel of
	// SCALE), with the centre of each segment, to evaluate: the segments that Earth Engine gives (one fewer if it
	// measures the line a hair shorter: transectRows leaves the last row empty)
	function transectStats(value, dem, line, cuts, scale, crs) {
		var segments = ee.List(ee.Geometry(line).cutLines(cuts, 1).geometries());
		var fc = ee.FeatureCollection(ee.List.sequence(0, segments.size().subtract(1)).map(function (i) {
			var g = ee.Geometry(segments.get(i));
			return ee.Feature(g.buffer(scale / 2, 1), {i: i, centre: g.centroid(1).coordinates()});
		}));
		return ee.Image.cat([ee.Image(value).rename('value'), ee.Image(dem).rename('elevation')]).reduceRegions({
			collection: fc, reducer: ee.Reducer.mean(), scale: scale, crs: crs, tileScale: 4});
	}

	// The rows {distance_m, lon, lat, value, elevation} of the evaluated FEATURES of transectStats
	function transectRows(features, cuts, length) {
		var by = {};
		features.forEach(function (f) { by[Math.round(f.properties.i)] = f.properties; });
		var out = [];
		for (var i = 0; i <= cuts.length; i++) {
			var p = by[i] || {}, a = i ? cuts[i - 1] : 0, b = i < cuts.length ? cuts[i] : length;
			var c = p.centre || [null, null];
			out.push({distance_m: (a + b) / 2, lon: c[0], lat: c[1], value: p.value === undefined ? null : p.value,
				elevation: p.elevation === undefined ? null : p.elevation});
		}
		return out;
	}

	// The changes of a land cover map between two years (classes.pairs, transition_rows, broad_transitions)
	var PAIR = 1000;

	function pairs(first, other) {
		return ee.Image(first).multiply(PAIR).add(ee.Image(other)).toInt().rename('class');
	}

	function transitionRows(features, m, year, otherYear) {
		var out = [], seen = {};
		features.forEach(function (f) {
			var name = String(f.properties.name);  // classes.numbered: those of the same name, 'Sierra Nevada (2)'
			seen[name] = (seen[name] || 0) + 1;
			var region = seen[name] > 1 ? name + ' (' + seen[name] + ')' : name;
			var by = (f.properties.groups || []).map(function (g) { return [Math.round(g['class']), g.sum]; });
			var total = by.reduce(function (a, g) { return a + g[1]; }, 0);
			by.sort(function (a, b) { return b[1] - a[1]; });
			by.forEach(function (g) {
				var a = Math.floor(g[0] / PAIR), b = g[0] % PAIR;
				out.push({region: region, map: m.name, year: year, other_year: otherYear,
					from_class: a, from_label: a + ' ' + (m.names[String(a)] || ''), from_landcover: m.classes[String(a)] || null,
					to_class: b, to_label: b + ' ' + (m.names[String(b)] || ''), to_landcover: m.classes[String(b)] || null,
					ha: g[1], percent: total ? 100 * g[1] / total : null});
			});
		});
		return out;
	}

	function broadTransitions(rows, lang) {
		var acc = {}, keys = [];
		var order = landcoverClasses().map(function (c) { return c.key; });
		rows.forEach(function (r) {
			var k = [r.region, r.from_landcover, r.to_landcover].join('|');
			if (!acc[k]) {
				keys.push(k);
				acc[k] = {region: r.region, from_landcover: r.from_landcover, to_landcover: r.to_landcover,
					from_label: landcoverName(r.from_landcover, lang), to_label: landcoverName(r.to_landcover, lang),
					ha: 0, percent: 0};
			}
			acc[k].ha += r.ha;
			acc[k].percent += r.percent || 0;
		});
		var pos = function (k) { var i = order.indexOf(k); return i < 0 ? order.length : i; };
		return keys.map(function (k) { return acc[k]; }).sort(function (a, b) {
			return a.region < b.region ? -1 : a.region > b.region ? 1 :
				pos(a.from_landcover) - pos(b.from_landcover) || pos(a.to_landcover) - pos(b.to_landcover);
		});
	}

	function landcoverName(key, lang) {
		var c = landcoverClasses().filter(function (x) { return x.key === key; })[0];
		return c ? (c[lang] || c.en) : key;
	}

	// The search of the Earth Engine data catalog (services.find_datasets, monitoreo.eecatalog), in its slim copy of
	// catalog.js (build.py: eecatalogIndex): the words of TEXT, at least half of them, in the title or ID (3 points
	// each) or the keywords (1), those with most words first; the collections of images with data in the years FIRST
	// to LAST (the images, fixed layers without dates, whatever their dates); at most LIMIT
	function catalogLow(text) {
		return String(text || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
			.replace(/[^a-z0-9.\-_/]+/g, ' ').trim();
	}

	function searchCatalog(text, first, last, limit) {
		var words = catalogLow(text).split(' ').filter(Boolean);
		var found = [];
		((CATALOG.eecatalog || {}).datasets || []).forEach(function (d, i) {
			if (d[2] && first && d[4] !== null && d[4] !== undefined && d[4] < first) return;
			if (d[2] && last && d[3] !== null && d[3] !== undefined && d[3] > last) return;
			var head = catalogLow(d[1] + ' ' + d[0]), tail = catalogLow(d[5]), n = 0, score = 0;
			words.forEach(function (w) {
				if (head.indexOf(w) >= 0) { n++; score += 3; } else if (tail.indexOf(w) >= 0) { n++; score += 1; }
			});
			if (words.length && n * 2 < words.length) return;
			found.push([n, score, i, d]);
		});
		found.sort(function (a, b) { return b[0] - a[0] || b[1] - a[1] || a[2] - b[2]; });
		return found.slice(0, limit || 20).map(function (f) {
			var d = f[3];
			return {id: d[0], title: d[1], type: d[2] ? 'image_collection' : 'image', first: d[3], last: d[4]};
		});
	}

	// animation.range_image: the map of S over REGIONS whose percentiles 5 and 95 colour every frame, that of the whole
	// period or, for a METRIC of TOTALS (sum, count), which grows with the images, the median of the frames of STEPS
	// (that of the whole period would be that of all the steps, as many times bigger as they are)
	function animationRange(s, regions, steps, metric) {
		var geom = regions.geometry();
		if (TOTALS.indexOf(String(metric).trim().toLowerCase()) < 0) return image(s, geom).clipToCollection(regions);
		var col = collection(s, geom);
		return ee.ImageCollection.fromImages(steps.map(function (b) {
			return reduceSpan(col, metric, b[0], b[1]);
		})).median().rename('value').clipToCollection(regions);
	}

	// ee.List of the days with images ('YYYY-MM-dd') of the period of S, to evaluate: then dailyBins
	function dailyDays(s, region) {
		var wins = windows(s.period, s.season);
		var col = collection(s, region).filter(dateFilter(wins));
		return col.aggregate_array('system:time_start').map(function (t) {
			return ee.Date(t).format('YYYY-MM-dd');
		}).distinct().sort();
	}

	function dailyBins(days) {
		return days.map(function (d) { return [d, iso(addDays(date(d), 1))]; });
	}

	// What autoScale and the CRS need, to evaluate once: {area: of the biggest region (m²), centroid: [lon, lat] and
	// bounds: the coordinates of their bounding box (for regionCrs), total: area of all the regions and boundsArea: of
	// their bounding box (m²)}
	// the longitude of the corner I of the bounds of GEOM (0: west, 2: east), on the server
	function boundsLon(geom, i) {
		return ee.Number(ee.List(ee.List(ee.List(geom.bounds(1000).coordinates()).get(0)).get(i)).get(0));
	}

	function regionInfo(regions) {
		var geom = regions.geometry();
		return ee.Dictionary({
			area: regions.map(function (f) { return ee.Feature(null, {a: f.geometry().area(1)}); }).aggregate_max('a'),
			centroid: geom.centroid(1000).coordinates(),
			bounds: geom.bounds(1000).coordinates(),
			// areas.auto_crs: across the antimeridian (bounds of 360 degrees), its bounds in PACIFIC_CRS too, for its span
			pacific: ee.Algorithms.If(boundsLon(geom, 2).subtract(boundsLon(geom, 0)).gt(359),
				geom.bounds(1000, PACIFIC_CRS).coordinates(), null),
			total: geom.area(1000),
			boundsArea: geom.bounds(1000).area(1000)
		});
	}

	// areas.is_large: whether a region of AREA m² is a large area (more than LARGE_AREA_KM2)
	function isLarge(area) {
		return Boolean(area) && area > LARGE_AREA_KM2 * 1e6;
	}

	// areas.default_scale: the pixel (m) of the statistics of a region whose biggest feature has AREA m², with data of
	// NATIVE m: that of the data, or bigger so that it has about TARGET pixels (rounded up to NICE_SCALES); in a large
	// area (isLarge), 1 to 10 km (LARGE_PIXEL), never finer than the data
	function defaultScale(native, area, target) {
		native = Number(native);
		var need = area ? Math.sqrt(area / target) : 0, scale = native;
		if (need > native) {
			scale = NICE_SCALES.filter(function (n) { return n >= need; })[0] || NICE_SCALES[NICE_SCALES.length - 1];
		}
		if (isLarge(area)) scale = Math.max(native, Math.min(Math.max(scale, LARGE_PIXEL[0]), LARGE_PIXEL[1]));
		return scale;
	}

	// timeseries.auto_scale, from the AREA of the biggest region (m²)
	function autoScale(entry, area) {
		return defaultScale(entry.m, area, TARGET_PIXELS);
	}

	// timeseries.table: ee.FeatureCollection with a row (region, date, value, n_pixels, n_images) per step of STEPS
	// and region of REGIONS, computed on pixels of SCALE metres in CRS
	function seriesTable(s, regions, metric, stat, scale, steps, crs, tileScale) {
		var col = collection(s, regions.geometry(), scale);
		checkMetric(metric);
		var red = metric;
		// the statistic count is the number of pixels: once (Earth Engine refuses two outputs count)
		var sred = String(stat).trim().toLowerCase() === 'count' ? ee.Reducer.count() :
			reducer(stat).combine(ee.Reducer.count(), '', true);
		var out = ee.String(reducer(stat).getOutputs().get(0));
		var bands = steps.map(function (st, i) { return 's' + i; });
		var img = ee.Image.cat(steps.map(function (st, i) {
			return reduceSpan(col, red, st[0], st[1]).rename(bands[i]);
		}));
		var nImages = ee.List(steps.map(function (st) { return col.filterDate(st[0], st[1]).size(); }));
		var stats = img.reduceRegions({collection: regions, reducer: sred, scale: scale, crs: crs,
			tileScale: tileScale || 4});
		var prefix = bands.map(function (b) { return bands.length > 1 ? b + '_' : ''; });
		return stats.map(function (f) {
			f = ee.Feature(f);
			return ee.FeatureCollection(steps.map(function (st, i) {
				return ee.Feature(null, {region: f.get('name'), date: st[0], value: statValue(f, stat, out, prefix[i]),
					n_pixels: f.get(prefix[i] + 'count'), n_images: nImages.get(i)});
			}));
		}).flatten();
	}

	// timeseries.series (with timeseries._fetch): the rows of STEPS, requested in blocks of at most MAX_ROWS rows,
	// split in two when Earth Engine runs out of memory or time and repeated when it is busy.
	// done(error, rows), progress(done steps, total) after each block.
	function series(s, regions, nRegions, metric, stat, scale, crs, steps, done, progress) {
		onlyMetric(entryOf(s), metric);
		var block = Math.max(1, Math.min(Math.floor(MAX_ROWS / Math.max(nRegions, 1)), MAX_STEPS));
		var blocks = [];
		for (var i = 0; i < steps.length; i += block) blocks.push(steps.slice(i, i + block));
		var rows = [];
		var count = 0;
		var noted = NOTES;  // those of the computation of this series: its blocks note in them, whenever they come

		function fetch(part, attempt, next) {
			withNotes(noted, function () {
				return seriesTable(s, regions, metric, stat, scale, part, crs);
			}).evaluate(function (fc, error) {
				if (!error) {
					fc.features.forEach(function (f) {
						var r = {value: null, n_pixels: 0};
						for (var k in f.properties) r[k] = f.properties[k];
						r.region = String(r.region);
						rows.push(r);
					});
					return next();
				}
				var msg = String(error).toLowerCase();
				var split = SPLIT_ERRORS.some(function (e) { return msg.indexOf(e) >= 0; });
				var retry = RETRY_ERRORS.some(function (e) { return msg.indexOf(e) >= 0; });
				if (split && part.length > 1) {
					var half = Math.floor(part.length / 2);
					return fetch(part.slice(0, half), 0, function () { fetch(part.slice(half), 0, next); });
				}
				if (attempt >= 3 || !(split || retry)) return done(error);
				setTimeout(function () { fetch(part, attempt + 1, next); }, Math.pow(2, attempt) * 5000);
			});
		}

		function run(k) {
			if (k === blocks.length) {
				rows.sort(function (a, b) {
					return a.region < b.region ? -1 : a.region > b.region ? 1 : a.date < b.date ? -1 : a.date > b.date ? 1 : 0;
				});
				return done(null, rows);
			}
			fetch(blocks[k], 0, function () {
				count += blocks[k].length;
				if (progress) progress(count, steps.length);
				run(k + 1);
			});
		}

		run(0);
	}

	// By day of the year (timeseries.with_doy and doy_profile): a line per year, or the seasonal profile, a metric
	// between the years (overYears) of the values of each step of the year, a line per variable -------------------

	var INTERANNUAL = ['mean', 'median', 'min', 'max', 'std', 'cv'];  // timeseries.INTERANNUAL, and pN
	var INTERANNUAL_TEXT = 'mean, median, min, max, std (sample standard deviation), cv (coefficient of variation, %) ' +
		'or pN (percentile N, e.g. p25)';
	var PROFILE_COLUMNS = ['region', 'variable', 'part', 'doy', 'label', 'value', 'n_years'];
	// timeseries.PROFILE_META: the columns of the CSV of a profile after PROFILE_COLUMNS
	var PROFILE_META = ['sensor', 'step', 'metric', 'stat', 'interannual', 'unit', 'scale_m'];
	var MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
	var COMMON_YEAR = 2023;  // a year of 365 days, for the names of the days of the year
	var LEAP_YEAR = 2024;  // a year of 366 days, for the days of the year of the calendar days
	var MONTH_STARTS = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];  // charts.MONTH_STARTS

	// The day of the year (1-366) of the date D (UTC)
	function dayOfYear(d) {
		return Math.round((d - Date.UTC(d.getUTCFullYear(), 0, 1)) / 864e5) + 1;
	}

	// timeseries.with_doy: ROWS with the year and the day of the year (1-366) of the first day of each step
	function withDoy(rows) {
		rows.forEach(function (r) {
			var d = date(String(r.date).slice(0, 10));
			r.year = d.getUTCFullYear();
			r.doy = dayOfYear(d);
		});
		return rows;
	}

	// timeseries.check_interannual: METRIC between the years in lower case, or an error
	function checkInterannual(metric) {
		var m = String(metric === null || metric === undefined ? '' : metric).trim().toLowerCase();
		var p = /^p(\d+(?:\.\d+)?)$/.exec(m);
		if (INTERANNUAL.indexOf(m) >= 0 || (p && Number(p[1]) >= 0 && Number(p[1]) <= 100)) return m;
		throw new Error('unknown metric between the years (interannual) ' + metric + ': use ' + INTERANNUAL_TEXT);
	}

	// timeseries.over_years: METRIC of VALUES (one per year; the null left out), or null without values: the mean;
	// the median (the mean of the two middle values when they are even); min; max; std, the sample standard deviation
	// (n - 1; null with fewer than 2 values); cv, 100 × std / |mean| (null with fewer than 2 values or a mean of 0); pN,
	// the percentile N with linear interpolation between the closest ranks. The sums add the values in their order,
	// one by one, as Python, so that both give the same numbers
	function overYears(values, metric) {
		var m = checkInterannual(metric);
		var xs = values.filter(function (v) { return v !== null && v !== undefined; }).map(Number);
		var n = xs.length;
		if (!n) return null;
		function mean() {
			var total = 0;
			for (var i = 0; i < n; i++) total += xs[i];
			return total / n;
		}
		function std() {
			var mu = mean(), total = 0;
			for (var i = 0; i < n; i++) {
				var d = xs[i] - mu;
				total += d * d;
			}
			return Math.sqrt(total / (n - 1));
		}
		if (m === 'mean') return mean();
		if (m === 'min' || m === 'max') return Math[m].apply(null, xs);
		if (m === 'std' || m === 'cv') {
			if (n < 2) return null;
			if (m === 'std') return std();
			var mu = mean();
			return mu === 0 ? null : 100 * std() / Math.abs(mu);
		}
		var s = xs.slice().sort(function (a, b) { return a - b; });
		if (m === 'median') return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
		var rank = Number(m.slice(1)) / 100 * (n - 1);
		var lo = Math.floor(rank), hi = Math.min(lo + 1, n - 1);
		return s[lo] + (s[hi] - s[lo]) * (rank - lo);
	}

	// timeseries.day_label: the name in English of the day of the year DOY in a common year ('Jan 17'; 366: 'Dec 31')
	function dayLabel(doy) {
		var d = addDays(ymd(COMMON_YEAR, 1, 1), Math.min(Math.max(Math.floor(Number(doy)), 1), 365) - 1);
		return MONTH_ABBR[d.getUTCMonth()] + ' ' + d.getUTCDate();
	}

	// timeseries._split_month: [month, first day] of the SEASON (['MM-DD', 'MM-DD']) when it starts and ends in the same
	// month and crosses the new year (15 October to 14 October), whose windows have two parts of that month; else null
	function splitMonth(season) {
		if (!season) return null;
		var a = String(season[0]).split('-').map(Number), b = String(season[1]).split('-').map(Number);
		return a[0] === b[0] && a[1] > b[1] ? a : null;
	}

	function pad2(n) {
		return (n < 10 ? '0' : '') + n;
	}

	// timeseries._part_of: the step of the year of the first day DAY of a step of STEP: the month (1-12), or 'MM-DD' for
	// the part of a month from the first day of a SEASON that starts and ends in it ('10-15'); the number of the 16-day
	// period from the start of its window of WINS (1 January, or the first day of the SEASON), 0, 1, 2, ..., the closest
	// one to DAY and none after the last one of the window; or the calendar day 'MM-DD'
	function partOf(day, step, wins, season) {
		if (step === 'monthly') {
			var split = splitMonth(season);
			if (split && day.getUTCMonth() + 1 === split[0] && day.getUTCDate() >= split[1]) {
				return pad2(split[0]) + '-' + pad2(split[1]);
			}
			return day.getUTCMonth() + 1;
		}
		if (step === 'daily') return iso(day).slice(5);
		var year = day.getUTCFullYear(), end = null;
		for (var i = 0; i < wins.length; i++) {
			if (wins[i][1] <= day && day < wins[i][2]) {
				year = wins[i][0];
				end = wins[i][2];
				break;
			}
		}
		var first = season ? md(year, season[0]) : ymd(year, 1, 1);
		var part = Math.floor(Math.round((day - first) / 864e5) / 16 + 0.5);
		return end ? Math.min(part, Math.floor((Math.round((end - first) / 864e5) - 1) / 16)) : part;
	}

	// timeseries._part_doy: the day of the year where the step of the year PART of STEP is drawn: monthly the median
	// (rounded, .5 up) of the days of the year DOYS of its rows; daily that of the calendar day in a leap year (29
	// February 60, 1 March 61); 16-day that of the first day of the period in a common year (the first day of the window
	// + 16 × PART days), which goes on after 31 December
	function partDoy(part, step, season, doys) {
		if (step === 'daily') return dayOfYear(ymd(LEAP_YEAR, Number(part.slice(0, 2)), Number(part.slice(3))));
		if (step === '16-day') {
			var first = season ? md(COMMON_YEAR, season[0]) : ymd(COMMON_YEAR, 1, 1);
			return (dayOfYear(first) - 1 + 16 * part) % 365 + 1;
		}
		doys = doys.slice().sort(function (a, b) { return a - b; });
		var k = doys.length;
		return Math.floor((k % 2 ? doys[(k - 1) / 2] : (doys[k / 2 - 1] + doys[k / 2]) / 2) + 0.5);
	}

	// timeseries._part_label: the name in English of the step of the year PART of STEP drawn on the day DOY: the month,
	// or its two parts in a season that starts and ends in it ('Oct 15-31', 'Oct 1-14'); the calendar day; the day of DOY
	function partName(part, step, season, doy) {
		if (step === 'monthly') {
			var split = splitMonth(season);
			if (typeof part === 'string') {
				return MONTH_ABBR[split[0] - 1] + ' ' + split[1] + '-' + daysInMonth(COMMON_YEAR, split[0]);
			}
			if (split && part === split[0]) return MONTH_ABBR[part - 1] + ' 1-' + (split[1] - 1);
			return MONTH_ABBR[part - 1];
		}
		if (step === 'daily') return MONTH_ABBR[Number(part.slice(0, 2)) - 1] + ' ' + Number(part.slice(3));
		return dayLabel(doy);
	}

	// timeseries.doy_profile: the seasonal profile of the time series ROWS ([{region, date, value, ...}], with variable
	// when they are of two variables, else VARIABLE, its name) of a STEP shorter than a year: [{region, variable, part,
	// doy, label, value, n_years}] (PROFILE_COLUMNS), a row per region, variable and step of the year (partOf), whose
	// value is INTERANNUAL (overYears) of its values in the years (n_years: how many are not null); doy is where it is
	// drawn (partDoy), label its name (partName). The features of the same name are numbered from the second one
	// ('Sierra Nevada (2)'): the rows of each date come in the order of the features (series). Sorted by region,
	// variable (in the order of ROWS), doy and part. S needs period and season only for the 16-day and monthly steps
	function doyProfile(rows, s, step, interannual, variable) {
		if (STEPS.indexOf(step) < 0 || step === 'annual') {
			throw new Error('the profile by day of the year needs a step shorter than a year: daily, 16-day or monthly, ' +
				'not ' + step);
		}
		interannual = checkInterannual(interannual);
		var season = step !== 'daily' && s ? s.season || null : null;
		var wins = step === '16-day' ? windows(s.period, season) : [];
		var groups = {}, keys = [], names = [], seen = {};
		rows.forEach(function (r) {
			var text = String(r.date).slice(0, 10), day = date(text);
			var name = r.variable || variable || '';
			if (names.indexOf(name) < 0) names.push(name);
			var region = String(r.region), id = [region, name, text].join('\u0000');
			seen[id] = (seen[id] || 0) + 1;
			if (seen[id] > 1) region += ' (' + seen[id] + ')';
			var part = partOf(day, step, wins, season);
			var key = [region, name, part].join('\u0000');
			if (!groups.hasOwnProperty(key)) {
				groups[key] = {region: region, name: name, part: part, items: []};
				keys.push(key);
			}
			groups[key].items.push([text, r.doy || dayOfYear(day), r.value === undefined ? null : r.value]);
		});
		var out = keys.map(function (key) {
			var g = groups[key];
			var items = g.items.slice().sort(function (a, b) { return a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0; });
			var doy = partDoy(g.part, step, season, items.map(function (x) { return x[1]; }));
			var values = items.map(function (x) { return x[2]; }).filter(function (v) { return v !== null; });
			return {region: g.region, variable: g.name, part: String(g.part), doy: doy,
				label: partName(g.part, step, season, doy), value: overYears(values, interannual), n_years: values.length};
		});
		out.sort(function (a, b) {
			return a.region < b.region ? -1 : a.region > b.region ? 1 :
				names.indexOf(a.variable) - names.indexOf(b.variable) || a.doy - b.doy ||
				(a.part < b.part ? -1 : a.part > b.part ? 1 : 0);
		});
		return out;
	}

	// catalog.UDUNITS and catalog.udunits (without per_year): the unit of the catalog (e.g. '[°C]') in UDUNITS ('degC'),
	// or '' if unknown; the units of the data of Earth Engine are already in UDUNITS ('mm day-1')
	var UDUNITS = {'[unitless]': '1', '[°C]': 'degC', '[kg/m²/8 days]': 'kg m-2 (8 day)-1', '[J/m²/day]': 'J m-2 day-1',
		'[mg m⁻³]': 'mg m-3', '[%]': '%', '[m]': 'm', '[°]': 'degree', '[mm]': 'mm', '[mm/month]': 'mm month-1',
		'[mm/day]': 'mm day-1', '[kPa]': 'kPa', '[days]': 'day',  // [days]: the snow cover days
		'[class]': ''};  // [class]: class codes, without a unit (catalog.UDUNITS)

	function udunits(unit) {
		var text = String(unit || '').replace(/º/g, '°').trim();
		var u = UDUNITS.hasOwnProperty(text) ? UDUNITS[text] : '';
		return !u && text.charAt(0) !== '[' && UDUNITS_TEXT.test(text) ? text : u;
	}

	// Trends and comparisons (trends.py) ----------------------------------------------------------------------------

	var TREND_STEPS = ['monthly', '16-day', 'annual'];
	var OUTPUTS = ['slope', 'tau', 'z', 'p_value', 'intercept', 'n'];
	var MIN_YEARS = 2;
	var MONTHS = {
		es: ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
			'noviembre', 'diciembre'],
		en: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
			'November', 'December']
	};
	var DIVERGING = ['a50026', 'd73027', 'f46d43', 'fdae61', 'fee08b', 'ffffbf', 'd9ef8b', 'a6d96a', '66bd63', '1a9850',
		'006837'];
	var P_VALUE = ['0571b0', '92c5de', 'f7f7f7'];
	var YEARS = ['fde725', '5ec962', '21918c', '3b528b', '440154'];

	function parts(step) {
		if (step === 'monthly') return [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
		if (step === '16-day') {
			var out = [];
			for (var i = 1; i <= 23; i++) out.push(i);
			return out;
		}
		if (step === 'annual') return [0];
		throw new Error('unknown step ' + step + ' for trends and comparisons: use ' + TREND_STEPS.join(', '));
	}

	function pad(n) {
		return (n < 10 ? '0' : '') + n;
	}

	function partKey(step, part) {
		return step === 'monthly' ? 'm' + pad(part) : step === '16-day' ? 'p' + pad(part) : 'all';
	}

	function partLabel(step, part, lang) {
		lang = lang === 'en' ? 'en' : 'es';
		if (step === 'monthly') return MONTHS[lang][part - 1];
		if (step === '16-day') {
			var first = (part - 1) * 16 + 1;
			return (lang === 'en' ? 'days ' : 'días ') + first + '-' + Math.min(first + 15, 366);
		}
		return lang === 'en' ? 'year' : 'año';
	}

	// trends._part_span
	function partSpan(step, part, year) {
		if (step === 'monthly') return [ymd(year, part, 1), ymd(year, part + 1, 1)];
		if (step === '16-day') {
			var first = addDays(ymd(year, 1, 1), (part - 1) * 16);
			return [first, minDate(addDays(first, 16), ymd(year + 1, 1, 1))];
		}
		return [ymd(year, 1, 1), ymd(year + 1, 1, 1)];
	}

	// trends.seasonal_bins: [part, year, first day, day after the last]
	function seasonalBins(s, step) {
		parts(step);
		var out = [];
		windows(s.period, s.season).forEach(function (w) {
			var year = w[0], ws = w[1], we = w[2];
			if (step === 'annual') {
				out.push([0, year, iso(ws), iso(we)]);
				return;
			}
			for (var y = ws.getUTCFullYear(); y <= we.getUTCFullYear(); y++) {
				parts(step).forEach(function (u) {
					var sp = partSpan(step, u, y);
					var a = maxDate(sp[0], ws), b = minDate(sp[1], we);
					if (a < b) out.push([u, year, iso(a), iso(b)]);
				});
			}
		});
		return out;
	}

	// trends.yearly_collection
	function yearlyCollection(s, region, step, part, metric) {
		onlyMetric(entryOf(s), metric || 'mean');
		var col = collection(s, region);
		var red = metric || 'mean';
		checkMetric(red);
		var imgs = [];
		seasonalBins(s, step).forEach(function (b) {
			if (b[0] !== part) return;
			var value = reduceSpan(col, red, b[2], b[3]);
			imgs.push(ee.Image.constant(b[1]).toFloat().rename('t').updateMask(value.mask()).addBands(value));
		});
		if (!imgs.length) throw new Error('the period has no ' + partLabel(step, part, 'en'));
		return ee.ImageCollection.fromImages(imgs);
	}

	// trends.trend_image
	function trendImage(s, region, step, part, metric, minYears) {
		var col = yearlyCollection(s, region, step, part, metric);
		var first = windows(s.period, s.season)[0][0];
		var n = col.select('value').count().rename('n');
		var tau = col.select('value').reduce(ee.Reducer.kendallsCorrelation()).select('value_tau').rename('tau');
		var z = tau.multiply(n.multiply(n.subtract(1)).multiply(9).divide(n.multiply(2).add(5).multiply(2)).sqrt())
			.rename('z');
		var p = ee.Image.constant(1).subtract(z.abs().divide(Math.sqrt(2)).erf()).rename('p_value');
		var sen = col.select(['t', 'value']).reduce(ee.Reducer.sensSlope());
		var slope = sen.select('slope');
		var intercept = sen.select('offset').add(slope.multiply(first)).rename('intercept');
		var out = ee.Image.cat([slope, tau, z, p, intercept, n.toFloat()]).rename(OUTPUTS);
		return out.updateMask(n.gte(minYears || MIN_YEARS));
	}

	// trends.vis
	function trendVis(output, lo, hi) {
		if (output === 'tau') return {min: -1, max: 1, palette: DIVERGING};
		if (output === 'p_value') return {min: 0, max: 0.1, palette: P_VALUE};
		if (output === 'slope' || output === 'z' || output === 'difference') {
			var m = Math.max(Math.abs(lo || 0), Math.abs(hi || 0)) || (output === 'z' ? 1.96 : 1e-6);
			return {min: -m, max: m, palette: DIVERGING};
		}
		if (output === 'n') return {min: lo === null || lo === undefined ? 0 : lo,
			max: hi === null || hi === undefined ? 10 : hi, palette: YEARS};
		return null;
	}

	// math.erfc (W. J. Cody's rational approximations, relative error below 1e-15)
	function erfc(x) {
		var ax = Math.abs(x), r;
		if (ax < 0.5) {
			var t = ax * ax;
			var top = (((0.185777706184603153 * t + 3.16112374387056560) * t + 113.864154151050156) * t +
				377.485237685302021) * t + 3209.37758913846947;
			var bot = (((t + 23.6012909523441209) * t + 244.024637934444173) * t + 1282.61652607737228) * t +
				2844.23683343917062;
			r = 1 - ax * top / bot;
		} else if (ax < 4) {
			var c = [2.15311535474403846e-8, 0.564188496988670089, 8.88314979438837594, 66.1191906371416295,
				298.635138197400131, 881.952221241769090, 1712.04761263407058, 2051.07837782607147, 1230.33935479799725];
			var d = [1, 15.7449261107098347, 117.693950891312499, 537.181101862009858, 1621.38957456669019,
				3290.79923573345963, 4362.61909014324716, 3439.36767414372164, 1230.33935480374942];
			var num = c[0] * ax, den = ax;
			for (var i = 1; i < 8; i++) {
				num = (num + c[i]) * ax;
				den = (den + d[i]) * ax;
			}
			r = Math.exp(-ax * ax) * (num + c[8]) / (den + d[8]);
		} else {
			var p = [0.305326634961232344, 0.360344899949804439, 0.125781726111229246, 0.0160837851487422766,
				6.58749161529837803e-4, 0.0163153871373020978];
			var q = [2.56852019228982242, 1.87295284992346725, 0.527905102951428412, 0.0605183413124413191,
				0.00233520497626869185];
			var z = 1 / (ax * ax), pn = p[5] * z, qn = z;
			for (var j = 0; j < 4; j++) {
				pn = (pn + p[j]) * z;
				qn = (qn + q[j]) * z;
			}
			var frac = z * (pn + p[4]) / (qn + q[4]);
			r = Math.exp(-ax * ax) / ax * (1 / Math.sqrt(Math.PI) - frac);
		}
		return x < 0 ? 2 - r : r;
	}

	// trends.mann_kendall: [n, tau, z, p_value] of VALUES against YEARS (null values left out)
	function sortedPoints(years, values) {
		var pts = [];
		years.forEach(function (x, i) {
			if (values[i] !== null && values[i] !== undefined) pts.push([x, values[i]]);
		});
		return pts.sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; });
	}

	function mannKendall(years, values) {
		var pts = sortedPoints(years, values), n = pts.length;
		if (n < 2) return [n, null, null, null];
		var s = 0;
		for (var i = 0; i < n; i++) {
			for (var j = i + 1; j < n; j++) s += (pts[j][1] > pts[i][1]) - (pts[j][1] < pts[i][1]);
		}
		var tau = s / (n * (n - 1) / 2);
		var z = tau * Math.sqrt(9 * n * (n - 1) / (2 * (2 * n + 5)));
		return [n, tau, z, erfc(Math.abs(z) / Math.SQRT2)];
	}

	function median(xs) {
		xs = xs.slice().sort(function (a, b) { return a - b; });
		var m = Math.floor(xs.length / 2);
		return xs.length % 2 ? xs[m] : (xs[m - 1] + xs[m]) / 2;
	}

	// trends.sen: [slope, intercept] of the Sen line; the intercept is its value in FIRST
	function sen(years, values, first) {
		var pts = sortedPoints(years, values);
		if (pts.length < 2) return [null, null];
		var slopes = [];
		for (var i = 0; i < pts.length; i++) {
			for (var j = i + 1; j < pts.length; j++) {
				if (pts[j][0] !== pts[i][0]) slopes.push((pts[j][1] - pts[i][1]) / (pts[j][0] - pts[i][0]));
			}
		}
		var slope = median(slopes);
		first = first === null || first === undefined ? pts[0][0] : first;
		return [slope, median(pts.map(function (p) { return p[1] - slope * (p[0] - first); }))];
	}

	function groupBy(rows, key) {
		var groups = {}, order = [];
		rows.forEach(function (r) {
			var k = key(r);
			if (!groups[k]) {
				groups[k] = [];
				order.push(k);
			}
			groups[k].push(r);
		});
		return {groups: groups, order: order};
	}

	function compareRegionPart(a, b) {
		return a.region < b.region ? -1 : a.region > b.region ? 1 : a.part - b.part;
	}

	// trends.trend_rows
	function trendRows(yearly, step, first, lang, minYears, alpha) {
		minYears = minYears || MIN_YEARS;
		alpha = alpha || 0.05;
		var g = groupBy(yearly, function (r) { return JSON.stringify([r.region, r.part]); });
		var out = g.order.map(function (k) {
			var rows = g.groups[k];
			var years = rows.map(function (r) { return r.year; });
			var values = rows.map(function (r) { return r.value; });
			var mk = mannKendall(years, values);
			var ok = mk[0] >= minYears && mk[1] !== null;
			var sl = ok ? sen(years, values, first) : [null, null];
			var valid = years.filter(function (x, i) { return values[i] !== null && values[i] !== undefined; });
			var r0 = rows[0];
			return {region: r0.region, part: r0.part, key: partKey(step, r0.part), label: partLabel(step, r0.part, lang),
				n: mk[0], tau: ok ? mk[1] : null, z: ok ? mk[2] : null, p_value: ok ? mk[3] : null,
				significant: Boolean(ok && mk[3] < alpha), slope: sl[0], intercept: sl[1],
				first_year: valid.length ? Math.min.apply(null, valid) : null,
				last_year: valid.length ? Math.max.apply(null, valid) : null};
		});
		return out.sort(compareRegionPart);
	}

	// Rows of seriesBins of seasonalBins with their part and year (services._seasonal_rows)
	function withParts(rows, sbins) {
		var partYear = {};
		sbins.forEach(function (b) { partYear[b[2]] = [b[0], b[1]]; });
		rows.forEach(function (r) {
			r.part = partYear[r.date][0];
			r.year = partYear[r.date][1];
		});
		return rows;
	}

	// trends.profile
	function profile(reference, other) {
		function means(rows) {
			var acc = {};
			rows.forEach(function (r) {
				if (r.value === null || r.value === undefined) return;
				var k = JSON.stringify([r.region, r.part]);
				(acc[k] = acc[k] || []).push(r.value);
			});
			var out = {};
			for (var k in acc) {
				out[k] = [acc[k].reduce(function (a, b) { return a + b; }, 0) / acc[k].length, acc[k].length];
			}
			return out;
		}
		var ref = means(reference), oth = means(other);
		var keys = {};
		reference.concat(other).forEach(function (r) { keys[JSON.stringify([r.region, r.part])] = [r.region, r.part]; });
		var out = Object.keys(keys).map(function (k) {
			var a = ref[k] || [null, 0], b = oth[k] || [null, 0];
			return {region: keys[k][0], part: keys[k][1], reference: a[0], other: b[0],
				difference: a[0] === null || b[0] === null ? null : b[0] - a[0], n_reference: a[1], n_other: b[1]};
		});
		return out.sort(compareRegionPart);
	}

	// The comparison image of services._comparison: bands difference (other - reference), reference and other
	function comparisonImage(ref, other, region) {
		checkDates(ref, 'comparisons of periods');
		var a = image(ref, region);
		var b = image(other, region);
		return ee.Image.cat([b.subtract(a), a, b]).rename(['difference', 'reference', 'other']);
	}

	// Burn severity (fire.py) ---------------------------------------------------------------------------------------

	var SEVERITY = [  // [class, lowest dNBR of the class, name es, name en]
		[-2, null, 'Rebrote alto', 'Enhanced regrowth, high'],
		[-1, -0.25, 'Rebrote bajo', 'Enhanced regrowth, low'],
		[0, -0.1, 'No quemado', 'Unburned'],
		[1, 0.1, 'Severidad baja', 'Low severity'],
		[2, 0.27, 'Severidad moderada-baja', 'Moderate-low severity'],
		[3, 0.44, 'Severidad moderada-alta', 'Moderate-high severity'],
		[4, 0.66, 'Severidad alta', 'High severity']
	];
	var BURNED = 0.1;
	// colours of the classes of UN-SPIDER (Recommended Practice: Burn Severity Mapping in Google Earth Engine), as
	// fire.COLOURS of the Python package
	var SEVERITY_COLOURS = ['7a8737', 'acbe4d', '0ae042', 'fff70b', 'ffaf38', 'ff641b', 'a41fd6'];

	// fire.RDNBR_SEVERITY: the classes of the RdNBR of Miller & Thode 2007 (their Table 4, without their factor 1000:
	// unchanged < 69, low 69-315, moderate 316-640, high >= 641 there), [class, lowest RdNBR of the class, name es,
	// name en]. 'Unchanged', not 'unburned': one year after the fire the area was indistinguishable from before it
	var RDNBR_SEVERITY = [
		[0, null, 'Sin cambios', 'Unchanged'],
		[1, 0.069, 'Severidad baja', 'Low severity'],
		[2, 0.316, 'Severidad moderada', 'Moderate severity'],
		[3, 0.641, 'Severidad alta', 'High severity']
	];
	var RDNBR_BURNED = 0.069;  // fire.RDNBR_BURNED: the RdNBR from which a pixel changed (class 1, low, and above)
	// fire.RDNBR_COLOURS, of the classes 0 to 3: the colours of UN-SPIDER of the classes of the dNBR of the same name
	// (unburned, low, moderate-high, high), so that both maps read alike (the article draws its classes in grey)
	var RDNBR_COLOURS = ['0ae042', 'fff70b', 'ff641b', 'a41fd6'];
	// fire.RDNBR_RANGE: the range of the colours of the map of the continuous RdNBR (the reversed diverging ramp, like
	// the RBR)
	var RDNBR_RANGE = [-1.2, 1.2];
	var RDNBR_MIN_NBR = 0.001;  // catalog.RDNBR_MIN_NBR: |NBR before| at least 0.001 (Howe et al. 2022)
	var RDNBR_COLUMNS = ['region', 'class', 'label', 'rdnbr_min', 'rdnbr_max', 'ha'];  // services.RDNBR_COLUMNS
	// fire.CLASSES: the burn indices with classes: their classes, colours, the value from which a pixel is burned (or
	// changed) and the name of the columns of the limits of their classes (dnbr_min and dnbr_max, rdnbr_min and
	// rdnbr_max)
	var CLASSES = {
		dNBR: {classes: SEVERITY, colours: SEVERITY_COLOURS, burned: BURNED, key: 'dnbr'},
		RdNBR: {classes: RDNBR_SEVERITY, colours: RDNBR_COLOURS, burned: RDNBR_BURNED, key: 'rdnbr'}
	};
	// services.BURN_INDICES and services.BURN_SENSORS: the burn indices and the sensors of each (those of its entries
	// of the catalog: NBR, RBR, RdNBR); RDNBR_MODIS, the collections of MODIS of the RdNBR (COLLECTION of
	// services.burn_severity: Terra, the default, since 2000-02-24, or Aqua, since 2002-07-04)
	var BURN_INDICES = ['dNBR', 'RBR', 'RdNBR'];
	var BURN_SENSORS = {dNBR: ['Sentinel-2', 'Landsat'], RBR: ['Sentinel-2', 'Landsat'],
		RdNBR: ['Sentinel-2', 'Landsat', 'Modis']};
	var RDNBR_MODIS = ['MODIS/061/MOD09GA', 'MODIS/061/MYD09GA'];

	// services.burn_severity: the burn index INDEX ('dNBR' by default, any case) checked with SENSOR and COLLECTION, the
	// same errors without Earth Engine
	function burnIndex(index, sensor, collection) {
		var low = String(index || 'dNBR').toLowerCase();
		var found = BURN_INDICES.filter(function (i) { return i.toLowerCase() === low; })[0];
		if (!found) {
			throw new Error('unknown burn index: use ' + BURN_INDICES.slice(0, -1).join(', ') + ' or ' +
				BURN_INDICES[BURN_INDICES.length - 1]);
		}
		var known = BURN_SENSORS[found].map(function (s) { return s.toLowerCase().replace(/ /g, ''); });
		if (sensor !== null && sensor !== undefined && known.indexOf(String(sensor).toLowerCase().replace(/ /g, '')) < 0) {
			throw new Error('the burn index ' + found + ' is computed with the sensors ' + BURN_SENSORS[found].join(', ') +
				', not ' + sensor + (String(sensor).toLowerCase() === 'modis' ? ': MODIS only with index RdNBR' : ''));
		}
		if (collection && found !== 'RdNBR') {
			throw new Error('collection is only for the index RdNBR with sensor Modis (MODIS/061/MOD09GA, Terra, or ' +
				'MODIS/061/MYD09GA, Aqua)');
		}
		return found;
	}

	// The entry of the catalog that services.burn_severity computes for INDEX with SENSOR (and COLLECTION, the MODIS
	// of the RdNBR: Terra without it), as catalog.find finds it (the first one): the NBR for the dNBR (101 Landsat,
	// 102 Sentinel-2), the RBR (103 Sentinel-2, 104 Landsat) and the RdNBR (144 Sentinel-2, 145 Landsat, 146 MODIS
	// Terra, 147 MODIS Aqua)
	function burnEntry(index, sensor, collection) {
		index = burnIndex(index, sensor, collection);
		var name = index === 'dNBR' ? 'NBR' : index;
		var low = function (s) { return String(s).toLowerCase().replace(/ /g, ''); };
		var found = variables().filter(function (e) {
			return low(e.index) === low(name) && (sensor === null || sensor === undefined || low(e.sensor) === low(sensor)) &&
				(!collection || e.col === collection);
		});
		if (!found.length) {
			throw new Error(name + ' with sensor ' + sensor + (collection ? ' and collection ' + collection : '') +
				' is not in the catalog of MonitorEO');
		}
		return found[0];
	}

	// fire._classes: the classes of INDEX ('dNBR', the default, or 'RdNBR', any case)
	function classesOf(index) {
		var low = String(index || 'dNBR').toLowerCase();
		for (var k in CLASSES) {
			if (k.toLowerCase() === low) return CLASSES[k];
		}
		throw new Error('the burn index ' + index + ' has no classes: use ' + Object.keys(CLASSES).join(' or '));
	}

	// fire.limits of the class in the position I of the classes of INDEX (the dNBR by default): [lowest, highest]
	// value of the index (null at the ends)
	function severityLimits(i, index) {
		var classes = classesOf(index).classes;
		return [classes[i][1], i + 1 < classes.length ? classes[i + 1][1] : null];
	}

	// fire.legend: the classes of INDEX ('dNBR', the default, or 'RdNBR') with their colours, for the legends of the
	// maps: [{value, label (in LANG, 'en' by default, or 'es'), color ('#rrggbb'), <key>_min, <key>_max}] (key: dnbr or
	// rdnbr), from the lowest class to high severity
	function severityLegend(index, lang) {
		var c = classesOf(index);
		return c.classes.map(function (k, i) {
			var lim = severityLimits(i, index);
			var out = {value: k[0], label: lang === 'es' ? k[2] : k[3], color: '#' + c.colours[i]};
			out[c.key + '_min'] = lim[0];
			out[c.key + '_max'] = lim[1];
			return out;
		});
	}

	// fire.class_label: the label of a class C (one of severityLegend or of severityTable) in a legend, with the values
	// of its index: «Low severity (dNBR 0.1 to 0.27)», «High severity (RdNBR ≥ 0.641)»; in LANG 'es' with a decimal
	// comma and «a»: «Severidad baja (RdNBR 0,069 a 0,316)»
	function classLabel(c, lang) {
		var es = lang === 'es';
		function num(v) {  // as '%.4g' of Python, for these values
			var s = v === 0 ? '0' : String(Number(Number(v).toPrecision(4)));
			return es ? s.replace('.', ',') : s;
		}
		function given(v) {
			return v !== null && v !== undefined;
		}
		// a class without them (of a categorical layer, see categoryLegend): its label as it is
		if (!['dnbr_min', 'dnbr_max', 'rdnbr_min', 'rdnbr_max'].some(function (k) { return k in c; })) return c.label;
		var key = 'rdnbr_min' in c || 'rdnbr_max' in c ? 'rdnbr' : 'dnbr';
		var low = c[key + '_min'], high = c[key + '_max'];
		var values = !given(low) ? '< ' + num(high) : !given(high) ? '≥ ' + num(low) :
			num(low) + (es ? ' a ' : ' to ') + num(high);
		return c.label + ' (' + (key === 'rdnbr' ? 'RdNBR' : 'dNBR') + ' ' + values + ')';
	}

	// fire.classify: the class of each pixel of the image VALUE of INDEX ('dNBR', the default, classes -2 to 4; or
	// 'RdNBR', classes 0 to 3), masked as it
	function classify(value, index) {
		var classes = classesOf(index).classes;
		var cls = ee.Image.constant(classes[0][0]);
		classes.slice(1).forEach(function (c) { cls = cls.add(value.gte(c[1])); });
		return cls.updateMask(value.mask()).toInt8().rename('severity');
	}

	// fire.rdnbr: the relative dNBR of Miller & Thode 2007, RdNBR = dNBR / sqrt(|NBR before|), with |NBR before| at
	// least RDNBR_MIN_NBR, on the scale of the dNBR (the article multiplies the NBR by 1000: 0.641 here is 641 there)
	function rdnbr(dnbr, nbrBefore) {
		return dnbr.divide(nbrBefore.abs().max(RDNBR_MIN_NBR).sqrt()).rename('rdnbr');
	}

	// services.burn_severity: {dnbr, severity, nbr_before, nbr_after (an image with these bands), hectares
	// (ee.FeatureCollection of the regions with the grouped hectares of each class)}. With INDEX 'RBR', burnRatio;
	// with 'RdNBR', rdnbrSeverity (BEFORE and AFTER, then, specs of their entries of the catalog: see burnEntry)
	function burnSeverity(before, after, regions, scale, crs, index) {
		index = burnIndex(index);
		if (index === 'RBR') return burnRatio(before, after, regions, scale, crs);
		if (index === 'RdNBR') return rdnbrSeverity(before, after, regions, scale, crs);
		var img = comparisonImage(before, after, regions.geometry()).clipToCollection(regions);
		var dnbr = img.select('reference').subtract(img.select('other')).rename('dnbr');
		var severity = classify(dnbr);
		var hectares = ee.Image.pixelArea().divide(1e4).addBands(severity).updateMask(dnbr.mask());
		var stats = hectares.reduceRegions({collection: regions, reducer: ee.Reducer.sum().group(1, 'class'),
			scale: scale, crs: crs, tileScale: 4});
		var bands = ['dnbr', 'severity', 'nbr_before', 'nbr_after'];
		return {image: ee.Image.cat([dnbr, severity.toFloat(), img.select('reference'), img.select('other')]).rename(bands),
			hectares: stats};
	}

	// services.burn_severity with index RBR (services._rbr): {image (bands rbr, dnbr, nbr_before, nbr_after), stats
	// (ee.FeatureCollection of the regions with the statistics of the RBR and the hectares with values)}. BEFORE and
	// AFTER are specs of the entry RBR of the catalog (103 Sentinel-2, 104 Landsat)
	var RBR_OFFSET = 1.001;  // catalog.RBR_OFFSET: RBR = dNBR / (NBR before + 1.001)
	var RBR_COLUMNS = ['region', 'mean', 'median', 'std', 'cv', 'p10', 'p90', 'min', 'max', 'ha'];

	// The statistics of services._rbr and services._rdnbr over each region (fire.stats_reducer): mean, median, standard
	// deviation (and from it the coefficient of variation), percentiles 10 and 90, minimum and maximum of the index, and
	// the sum of the hectares with values. The percentiles
	// from a histogram of PERCENTILE_BUCKETS buckets (fire.PERCENTILE_BUCKETS), so that a few outliers do not make them
	// coarse: with the default of Earth Engine, the percentile 10 and the median could be the same value
	var PERCENTILE_BUCKETS = 65536;
	function burnStatsReducer() {
		var percentiles = ee.Reducer.percentile([10, 50, 90], ['p10', 'median', 'p90'], PERCENTILE_BUCKETS);
		return ee.Reducer.mean().combine(percentiles, '', true).combine(ee.Reducer.stdDev(), '', true)
			.combine(ee.Reducer.minMax(), '', true).combine(ee.Reducer.sum(), '', true);
	}

	function burnRatio(before, after, regions, scale, crs) {
		var img = comparisonImage(before, after, regions.geometry()).clipToCollection(regions);
		var pre = img.select('reference'), post = img.select('other');
		var dnbr = pre.subtract(post).rename('dnbr');
		var rbr = dnbr.divide(pre.add(RBR_OFFSET)).rename('rbr');  // fire.rbr
		var stats = rbr.addBands(ee.Image.pixelArea().divide(1e4).updateMask(rbr.mask()).rename('ha')).reduceRegions({
			collection: regions, reducer: burnStatsReducer(), scale: scale, crs: crs, tileScale: 4});
		return {image: ee.Image.cat([rbr, dnbr, pre, post]).rename(['rbr', 'dnbr', 'nbr_before', 'nbr_after']),
			stats: stats};
	}

	// the rows of services._rbr from the features of the statistics of burnRatio
	function rbrTable(features) {
		return features.map(function (f) {
			var p = f.properties;
			return {region: String(p.name), mean: p.rbr_mean, median: p.rbr_median, std: p.rbr_stdDev,
				cv: cvNumber(p.rbr_mean, p.rbr_stdDev), p10: p.rbr_p10, p90: p.rbr_p90, min: p.rbr_min, max: p.rbr_max,
				ha: p.ha_sum || 0};
		});
	}

	// services.burn_severity with index RdNBR (services._rdnbr): {image (bands rdnbr, severity, dnbr, nbr_before,
	// nbr_after), hectares (ee.FeatureCollection of the regions with the grouped hectares of each class of
	// RDNBR_SEVERITY: see severityTable and burnedHa), stats (ee.FeatureCollection of the regions with the statistics of
	// the RdNBR and the hectares with values: see rdnbrTable)}. BEFORE and AFTER are specs of the entry RdNBR of the
	// catalog (144 Sentinel-2, 145 Landsat, 146 MODIS Terra, 147 MODIS Aqua: see burnEntry). Without the offset of the
	// article (the dNBR of an unburned area outside the fire), as the dNBR and the RBR
	function rdnbrSeverity(before, after, regions, scale, crs) {
		var img = comparisonImage(before, after, regions.geometry()).clipToCollection(regions);
		var pre = img.select('reference'), post = img.select('other');
		var dnbr = pre.subtract(post).rename('dnbr');
		var value = rdnbr(dnbr, pre);
		var severity = classify(value, 'RdNBR');
		var ha = ee.Image.pixelArea().divide(1e4).updateMask(value.mask());
		var hectares = ha.addBands(severity).reduceRegions({collection: regions,
			reducer: ee.Reducer.sum().group(1, 'class'), scale: scale, crs: crs, tileScale: 4});
		var stats = value.addBands(ha.rename('ha')).reduceRegions({collection: regions, reducer: burnStatsReducer(),
			scale: scale, crs: crs, tileScale: 4});
		var bands = ['rdnbr', 'severity', 'dnbr', 'nbr_before', 'nbr_after'];
		return {image: ee.Image.cat([value, severity.toFloat(), dnbr, pre, post]).rename(bands), hectares: hectares,
			stats: stats};
	}

	// the rows of the statistics of services._rdnbr (stats) from the features of the statistics of rdnbrSeverity
	function rdnbrTable(features) {
		return features.map(function (f) {
			var p = f.properties;
			return {region: String(p.name), mean: p.rdnbr_mean, median: p.rdnbr_median, std: p.rdnbr_stdDev,
				cv: cvNumber(p.rdnbr_mean, p.rdnbr_stdDev), p10: p.rdnbr_p10, p90: p.rdnbr_p90, min: p.rdnbr_min,
				max: p.rdnbr_max, ha: p.ha_sum || 0};
		});
	}

	// fire.table: rows of every class of INDEX ('dNBR', the default, or 'RdNBR') of a region from the GROUPS of the
	// grouped sum of hectares: {region, class, label (in LANG), <key>_min, <key>_max, ha} (key: dnbr or rdnbr)
	function severityTable(groups, region, lang, index) {
		var c = classesOf(index);
		var ha = {};
		(groups || []).forEach(function (g) { ha[Math.round(g['class'])] = g.sum; });
		return c.classes.map(function (k, i) {
			var lim = severityLimits(i, index);
			var row = {region: region, 'class': k[0], label: lang === 'en' ? k[3] : k[2]};
			row[c.key + '_min'] = lim[0];
			row[c.key + '_max'] = lim[1];
			row.ha = ha[k[0]] || 0;
			return row;
		});
	}

	// burned_ha of services.burn_severity (dNBR and RdNBR) from the ROWS of severityTable: {region: hectares of the
	// classes from 1 up, burned (dNBR ≥ 0.1) or changed (RdNBR ≥ 0.069)}, every region (0 if none)
	function burnedHa(rows) {
		var out = {};
		rows.forEach(function (r) {
			out[r.region] = (out[r.region] || 0) + (r['class'] >= 1 ? r.ha : 0);
		});
		return out;
	}

	// fire.PERIMETER_MIN_HA: the burned patches of less than these hectares are left out of the perimeter of the burned
	// area, and the unburned islands of less than them inside a patch filled (a minimum mapping unit)
	var PERIMETER_MIN_HA = 1;

	// fire.burned_min: the value of the burn INDEX from which a pixel is in the perimeter: VALUE if given (a number),
	// else that of its classes (dNBR 0.1, RdNBR 0.069); the RBR, without classes, needs VALUE
	function burnedMin(index, value) {
		if (value !== null && value !== undefined && value !== '') return Number(value);
		index = burnIndex(index);
		if (!CLASSES[index]) {
			throw new Error('the ' + index + ' has no classes: give the ' + index + ' from which a pixel is burned, for ' +
				'the perimeter of the burned area');
		}
		return CLASSES[index].burned;
	}

	// fire._rings: the coordinates of POLYGON (a list of rings in the ee.Projection PIXELS) without its holes of less
	// than MIN_M2 square metres (in CRS)
	function perimeterRings(polygon, pixels, crs, minM2) {
		var rings = ee.List(polygon);
		var holes = rings.slice(1).map(function (ring) {
			var area = ee.Geometry.Polygon(ee.List([ring]), pixels, false).area(1, crs);
			return ee.Algorithms.If(area.gte(minM2), ring, null);
		}, true);
		return ee.List([rings.get(0)]).cat(holes);
	}

	// fire.perimeter: the perimeter of the burned area of each feature of REGIONS, an ee.FeatureCollection of a
	// MultiPolygon (EPSG:4326) of the connected pixels (eight neighbours) of SCALE metres in CRS of the image VALUE (a
	// burn index) at least BURNED_MIN, without the patches of less than MIN_HA hectares and with the unburned islands of
	// less than MIN_HA filled, with the properties name, ha and patches
	function burnPerimeter(value, burnedMinValue, regions, scale, crs, minHa) {
		minHa = minHa === null || minHa === undefined ? PERIMETER_MIN_HA : Number(minHa);
		var burned = ee.Image(value).gte(burnedMinValue).selfMask().rename('burned');
		var minM2 = minHa * 1e4;
		var minPixels = minM2 / (scale * scale);
		// the polygons in the projection of the pixels (geometryInNativeProjection): CRS in units of SCALE metres
		var pixels = ee.Projection(crs).atScale(scale);
		function polygons(f) {
			var g = ee.Feature(f).geometry();
			var coords = ee.List(ee.Algorithms.If(ee.String(g.type()).equals('Polygon'), ee.List([g.coordinates()]),
				g.coordinates()));
			if (!(minM2 > 0)) return coords;  // with 0 ha, every island
			return coords.map(function (p) { return perimeterRings(p, pixels, crs, minM2); });
		}
		return ee.FeatureCollection(regions).map(function (region) {
			var geom = region.geometry();
			var patches = burned.clip(geom).reduceToVectors({geometry: geom, scale: scale, crs: crs,
				geometryType: 'polygon', eightConnected: true, maxPixels: 1e13, tileScale: 4,
				geometryInNativeProjection: true});
			var kept = patches.filter(ee.Filter.gte('count', minPixels));
			var coords = ee.List(kept.iterate(function (f, acc) { return ee.List(acc).cat(polygons(f)); }, ee.List([])));
			var shape = ee.Geometry.MultiPolygon(coords, pixels, false);
			return ee.Feature(shape.transform('EPSG:4326', scale / 10), {name: region.get('name'),
				ha: shape.area(1, crs).divide(1e4), patches: coords.size()});
		});
	}

	// Maps (maps.py) ------------------------------------------------------------------------------------------------

	var DEFAULT_PALETTE = ['000080', '0000FF', '0080FF', '00FFFF', '80FFFF', 'FFFFFF', 'FFFF00', 'FF8000', 'FF0000',
		'800000'];

	function ramp(entry, colours) {
		return (colours || (entry || {}).pm || DEFAULT_PALETTE).map(function (c) { return String(c).replace(/^#/, ''); });
	}

	// The percentiles 5 and 95 of a single band image over REGION, to evaluate: then visParams
	function percentiles(img, region, scale) {
		return ee.Image(img).rename('value').reduceRegion({reducer: ee.Reducer.percentile([5, 95]), geometry: region,
			scale: scale, bestEffort: true, maxPixels: 1e6, tileScale: 4});
	}

	// maps.vis_params from the evaluated percentiles
	function visParams(stats, entry, palette) {
		var lo = stats ? stats.value_p5 : null, hi = stats ? stats.value_p95 : null;
		if (lo === null || lo === undefined || hi === null || hi === undefined) {
			lo = entry && typeof entry.minp === 'number' ? entry.minp : 0;
			hi = entry && typeof entry.maxp === 'number' ? entry.maxp : 1;
		}
		if (hi === lo) hi = lo + 1e-6;
		return {min: lo, max: hi, palette: ramp(entry, palette)};
	}

	// services.spread: whether the values of a map with METRIC (and INTERANNUAL between the years, unless TEMPORAL is
	// 'period') are a spread (SPREAD: standard deviation, coefficient of variation), not in the range of the variable
	function spread(metric, temporal, interannual) {
		var ms = [metric].concat(temporal && temporal !== 'period' ? [interannual] : []);
		return ms.some(function (m) { return SPREAD.indexOf(String(m || '').trim().toLowerCase()) >= 0; });
	}

	// services.ramp_entry: the entry E for the colour ramp of its map: its palette, and the range of its values when
	// Earth Engine cannot compute it, that of the variable or, for a spread, 0 to 100 % for the coefficient of variation
	// and 0 to half the range of the variable for the standard deviation; the data of Earth Engine outside the catalog
	// (e.custom) as they are, without a range in the catalog (0 to 1, as rangeNoteData says)
	function rampEntry(e, metric, temporal, interannual) {
		if (!e || e.custom || !spread(metric, temporal, interannual)) return e;
		var out = {};
		for (var k in e) out[k] = e[k];
		if (isCv(metric) || (temporal && temporal !== 'period' && isCv(interannual))) {
			out.minp = 0;
			out.maxp = 100;
		} else {
			out.minp = 0;
			out.maxp = typeof e.minp === 'number' && typeof e.maxp === 'number' ? (e.maxp - e.minp) / 2 : 1;
		}
		return out;
	}

	// maps.RGB_STRETCH: percentiles of the reflectance of the true colour between which it is stretched; maps.RGB_RANGE:
	// the reflectance of the true colour when they cannot be computed
	var RGB_STRETCH = [2, 98];
	var RGB_RANGE = [0.0, 0.3];

	// The percentiles 2 and 98 of the bands red, green and blue of a true colour image over REGION (maps.rgb_vis), to
	// evaluate: then rgbVis
	function rgbPercentiles(img, region, scale) {
		return ee.Image(img).select(RGB_BANDS).reduceRegion({reducer: ee.Reducer.percentile(RGB_STRETCH), geometry: region,
			scale: scale, bestEffort: true, maxPixels: 1e6, tileScale: 4});
	}

	// maps.rgb_vis from the evaluated percentiles STATS (or VMIN and VMAX): the three bands stretched together between
	// the lowest percentile 2 and the highest percentile 98 of the bands (one range for the three, so that the colours
	// keep their balance); RGB_RANGE without them. {bands, min, max}
	function rgbVis(stats, vmin, vmax) {
		if (vmin === null || vmin === undefined || vmax === null || vmax === undefined) {
			var lows = RGB_BANDS.map(function (b) { return stats ? stats[b + '_p' + RGB_STRETCH[0]] : null; });
			var highs = RGB_BANDS.map(function (b) { return stats ? stats[b + '_p' + RGB_STRETCH[1]] : null; });
			var lo = RGB_RANGE[0], hi = RGB_RANGE[1];
			if (!lows.concat(highs).some(function (v) { return v === null || v === undefined; })) {
				lo = Math.min.apply(null, lows);
				hi = Math.max.apply(null, highs);
			}
			vmin = vmin === null || vmin === undefined ? lo : vmin;
			vmax = vmax === null || vmax === undefined ? hi : vmax;
		}
		if (vmax <= vmin) vmax = vmin + 1e-6;
		return {bands: RGB_BANDS.slice(), min: Number(vmin), max: Number(vmax)};
	}

	// The parameters of an analysis as JSON (parameters.py) ---------------------------------------------------------

	// parameters.ANALYSES: the analyses, the functions of monitoreo.services that compute; PARAMETER_OUTPUTS
	// (readme.NOT_ARGS): the outputs and callbacks of a call, not parameters of what was computed; parameters.META
	var PARAMETER_ANALYSES = ['time_series', 'time_series_to_drive', 'map_layer', 'map_figure', 'rgb_map', 'timelapse',
		'region_stats', 'transect', 'area_by_class', 'export_image', 'download_image', 'download_rgb', 'trend_table',
		'trend_map', 'download_trend', 'compare_series', 'compare_map', 'download_comparison', 'burn_severity'];
	var PARAMETER_OUTPUTS = ['csv', 'chart', 'path', 'thumbnail', 'progress', 'log', 'folder', 'tile', 'workers', 'record',
		'wait', 'drive_dir', 'overwrite', 'dry_run', 'quick'];
	var PARAMETER_META = ['monitoreo', 'analysis', 'parameters'];

	// parameters.read: the parameters of SOURCE, a JSON text or an object, as {monitoreo, analysis, parameters}; a flat
	// object ({"analysis": ..., "variable": ...}) is taken too: every key but monitoreo and analysis is a parameter. The
	// app reads no files: their text is pasted
	function readParameters(source) {
		if (typeof source === 'string') {
			var text = source.trim();
			if (text.charAt(0) !== '{') {
				throw new Error((text.length > 60 ? text.slice(0, 60) + '…' : text) + ': not a JSON object of parameters ' +
					'(the app reads no files: paste the text of the file)');
			}
			try {
				source = JSON.parse(text);
			} catch (e) {
				throw new Error('the parameters are not valid JSON: ' + e.message);
			}
		}
		if (!source || typeof source !== 'object' || Array.isArray(source)) {
			throw new Error('the parameters are a JSON object: {"monitoreo": ..., "analysis": ..., "parameters": {...}}');
		}
		var params = source.parameters, out = {}, k;
		if (!params || typeof params !== 'object' || Array.isArray(params)) {
			params = {};
			for (k in source) if (PARAMETER_META.indexOf(k) < 0) params[k] = source[k];
		}
		for (k in params) out[k] = params[k];
		return {monitoreo: source.monitoreo === undefined ? null : source.monitoreo,
			analysis: source.analysis === undefined ? null : source.analysis, parameters: out};
	}

	// json.dumps of VALUE as Python writes it (', ' and ': ' between the items), for parametersText
	function pyJson(value) {
		if (Array.isArray(value)) return '[' + value.map(pyJson).join(', ') + ']';
		if (value && typeof value === 'object') {
			return '{' + Object.keys(value).map(function (k) { return JSON.stringify(k) + ': ' + pyJson(value[k]); })
				.join(', ') + '}';
		}
		return value === undefined ? 'null' : JSON.stringify(value);
	}

	// parameters.text: the parameters that were not applied ([{name, value, reason}]), in a line: 'sensor ("MODIS"):
	// reason; ...'
	function parametersText(notApplied) {
		return (notApplied || []).map(function (p) {
			return p.name + ' (' + pyJson(p.value) + '): ' + p.reason;
		}).join('; ');
	}

	return {
		CATALOG: CATALOG, variables: variables, byRef: byRef, nameKey: nameKey, findEntry: findEntry, number: number,
		unitOf: unitOf, themes: themes, otherThemes: otherThemes,
		PARAMETER_ANALYSES: PARAMETER_ANALYSES, PARAMETER_OUTPUTS: PARAMETER_OUTPUTS, PARAMETER_META: PARAMETER_META,
		readParameters: readParameters, parametersText: parametersText,
		DATA_CATALOG: DATA_CATALOG, COMMUNITY_CATALOG: COMMUNITY_CATALOG, EE_ASSET: EE_ASSET, assetId: assetId,
		UNITS: UNITS, UNIT_WORDS: UNIT_WORDS, DIMENSIONLESS: DIMENSIONLESS, udunitsText: udunitsText,
		customUnit: customUnit, customEntry: customEntry, entryName: entryName, dataStem: dataStem,
		BAND_REDUCERS: BAND_REDUCERS, bandsOf: bandsOf, bandText: bandText, bandWords: bandWords, bandStem: bandStem,
		assetSource: assetSource, assetInfo: assetInfo, fromCollection: fromCollection, communityTheme: communityTheme,
		communityThemes: communityThemes, communityDatasets: communityDatasets, communityRecord: communityRecord,
		staticImage: staticImage, TWI: TWI, twiImage: twiImage, iso: iso, date: date, windows: windows, bins: bins,
		reducer: reducer, DAYS: DAYS, isDays: isDays, days: days, spans: spans, reduceSpan: reduceSpan,
		composite: composite, TEMPORAL: TEMPORAL,
		QUALITY: QUALITY, FILTERS: FILTERS, MEASURES: MEASURES, filters: filters, fixedFilters: fixedFilters,
		conflicts: conflicts,
		sensorCollection: sensorCollection, spec: spec, entryOf: entryOf, isStatic: isStatic, checkDates: checkDates,
		shortTitle: shortTitle, joinWords: joinWords, joinTitles: joinTitles, dataText: dataText, assetTitle: assetTitle,
		coverageParts: coverageParts, dataSource: dataSource, stepDays: stepDays, checkPeriod: checkPeriod,
		resetNotes: resetNotes, notes: notes, noteWarning: noteWarning, withNotes: withNotes, used: used,
		sourceText: sourceText,
		collection: collection, image: image, pinWhere: pinWhere, whereSpecs: whereSpecs, whereMask: whereMask,
		LANDCOVER_SHARE: LANDCOVER_SHARE, landcoverClasses: landcoverClasses, landcoverMaps: landcoverMaps,
		landcoverMap: landcoverMap, landcoverYears: landcoverYears, landcoverDefaultYear: landcoverDefaultYear,
		isLandcover: isLandcover, landcoverCheck: landcoverCheck, landcoverCodes: landcoverCodes,
		landcoverSource: landcoverSource, landcoverKeep: landcoverKeep, landcoverText: landcoverText,
		CLASS_SHARE: CLASS_SHARE, CLASS_STATS: CLASS_STATS, CLASS_GAP: CLASS_GAP, classTable: classTable,
		isCategorical: isCategorical, classCodes: classCodes, categoryName: categoryName, categoryLabel: categoryLabel,
		categoryColour: categoryColour, categoryGroupOf: categoryGroupOf, categoryGroupEntry: categoryGroupEntry,
		layerClasses: layerClasses, checkClasses: checkClasses, findClasses: findClasses,
		categoryLegend: categoryLegend, classVis: classVis, categoricalImage: categoricalImage, classesIn: classesIn,
		presentCodes: presentCodes, classCondition: classCondition, classKeep: classKeep, classText: classText,
		checkClassStats: checkClassStats, classConditions: classConditions, classZone: classZone,
		classZoneRows: classZoneRows, classAreaLegend: classAreaLegend, classGroupRows: classGroupRows,
		utmOf: utmOf, findProtectedAreas: findProtectedAreas, wdpaGeometries: wdpaGeometries, wdpaRegion: wdpaRegion,
		ecoregionAt: ecoregionAt, bboxRegion: bboxRegion, findAdminUnits: findAdminUnits, adminRegion: adminRegion,
		MUNICIPALITIES: MUNICIPALITIES, ADMIN_DATASETS: ADMIN_DATASETS, municipalityPlain: municipalityPlain,
		findMunicipalities: findMunicipalities, municipalityCodes: municipalityCodes,
		municipalityRegion: municipalityRegion, adminCredits: adminCredits, SEAS: SEAS, CITED_REGIONS: CITED_REGIONS,
		seaPlain: seaPlain, findSeas: findSeas, seaCodes: seaCodes, seaRegion: seaRegion, seaAt: seaAt, isSea: isSea,
		seaWarning: seaWarning, LARGE_AREA_KM2: LARGE_AREA_KM2, LARGE_PIXEL: LARGE_PIXEL, isLarge: isLarge,
		defaultScale: defaultScale, TARGET_PIXELS: TARGET_PIXELS,
		islandAt: islandAt, BIOME_MAX_ERROR: BIOME_MAX_ERROR, WITHIN_MAX_ERROR: WITHIN_MAX_ERROR,
		GLOBAL_CRS: GLOBAL_CRS, WIDE_DEGREES: WIDE_DEGREES, regionCrs: regionCrs, biomes: biomes, biomeName: biomeName,
		ecoregionsOfBiome: ecoregionsOfBiome, biomeCodes: biomeCodes, biomeFeature: biomeFeature,
		biomeRegion: biomeRegion, biomeAt: biomeAt, withinRegion: withinRegion,
		TREND_CLASSES: TREND_CLASSES, LANDCOVER_COLOURS: LANDCOVER_COLOURS, checkBreaks: checkBreaks,
		breakClasses: breakClasses, classifyBreaks: classifyBreaks, classifyTrend: classifyTrend, areaScale: areaScale,
		classHectares: classHectares, areaRows: areaRows, pairs: pairs, transitionRows: transitionRows,
		broadTransitions: broadTransitions, ZONE_STATS: ZONE_STATS, zoneStats: zoneStats, zoneRows: zoneRows,
		transectCuts: transectCuts, transectStats: transectStats, transectRows: transectRows,
		searchCatalog: searchCatalog,
		ANIMATION_STEPS: ANIMATION_STEPS, MAX_FRAMES: MAX_FRAMES, FRAME_COLOURS: FRAME_COLOURS, frameLabel: frameLabel,
		animationSteps: animationSteps, animationFrames: animationFrames, TOTALS: TOTALS,
		animationRange: animationRange,
		STEPS: STEPS, seriesBins: seriesBins, dailyDays: dailyDays, dailyBins: dailyBins, regionInfo: regionInfo,
		autoScale: autoScale, seriesTable: seriesTable, series: series,
		INTERANNUAL: INTERANNUAL, PROFILE_COLUMNS: PROFILE_COLUMNS, PROFILE_META: PROFILE_META, MONTH_ABBR: MONTH_ABBR,
		MONTH_STARTS: MONTH_STARTS, withDoy: withDoy, checkInterannual: checkInterannual, overYears: overYears,
		dayLabel: dayLabel, doyProfile: doyProfile, UDUNITS: UDUNITS, udunits: udunits,
		TREND_STEPS: TREND_STEPS, OUTPUTS: OUTPUTS, parts: parts, partKey: partKey, partLabel: partLabel,
		seasonalBins: seasonalBins, trendImage: trendImage, trendVis: trendVis, erfc: erfc, mannKendall: mannKendall,
		sen: sen, trendRows: trendRows, withParts: withParts, profile: profile, comparisonImage: comparisonImage,
		DIVERGING: DIVERGING, YEARS: YEARS, SEVERITY: SEVERITY, SEVERITY_COLOURS: SEVERITY_COLOURS, BURNED: BURNED,
		classify: classify, burnSeverity: burnSeverity, severityTable: severityTable, RBR_OFFSET: RBR_OFFSET,
		RBR_COLUMNS: RBR_COLUMNS, burnRatio: burnRatio, rbrTable: rbrTable,
		RDNBR_SEVERITY: RDNBR_SEVERITY, RDNBR_COLOURS: RDNBR_COLOURS, RDNBR_BURNED: RDNBR_BURNED,
		RDNBR_RANGE: RDNBR_RANGE, RDNBR_MIN_NBR: RDNBR_MIN_NBR, RDNBR_COLUMNS: RDNBR_COLUMNS, RDNBR_MODIS: RDNBR_MODIS,
		CLASSES: CLASSES, BURN_INDICES: BURN_INDICES, BURN_SENSORS: BURN_SENSORS, burnIndex: burnIndex,
		burnEntry: burnEntry, severityLimits: severityLimits, severityLegend: severityLegend, classLabel: classLabel,
		rdnbr: rdnbr, rdnbrSeverity: rdnbrSeverity, rdnbrTable: rdnbrTable, burnedHa: burnedHa,
		PERIMETER_MIN_HA: PERIMETER_MIN_HA, burnedMin: burnedMin, burnPerimeter: burnPerimeter,
		ramp: ramp, percentiles: percentiles, visParams: visParams, spread: spread, rampEntry: rampEntry,
		CV: CV, SPREAD: SPREAD, isCv: isCv, cv: cv, cvNumber: cvNumber, statValue: statValue,
		RGB: RGB, RGB_BANDS: RGB_BANDS, RGB_METRICS: RGB_METRICS, RGB_STRETCH: RGB_STRETCH, RGB_RANGE: RGB_RANGE,
		rgbOf: rgbOf, withRgb: withRgb, checkMetric: checkMetric, checkRgbMetric: checkRgbMetric, checkRgb: checkRgb,
		mosaic: mosaic, rgbPercentiles: rgbPercentiles, rgbVis: rgbVis
	};
})();
