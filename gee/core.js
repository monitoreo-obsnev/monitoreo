/*
 * MonitorEO in JavaScript: the core of the Python package monitoreo (src/monitoreo) ported to the Earth Engine
 * JavaScript API, for the app of the Code Editor (ui.js) and for the tests that compare both (tests/test_gee.py).
 *
 * It uses the globals ee and CATALOG (catalog.js, written by build.py from catalog.json with the formulas already
 * resolved to band names). ES5 only, as the Code Editor. Every function keeps the name and the behaviour of the
 * Python function it ports (module.function in the comments): change both together.
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
	var METRICS = 'mean, median, mode, min, max, sum, std, count or pN (percentile N, e.g. p95, p2.5)';
	// composite.RGB_METRICS: the metrics of the true colour (RGB) of the images of a variable: each band with the
	// metric (mean, median or pN), or, with max and min, the bands of the image where the variable is highest or lowest
	// on each pixel (composite.MOSAICS: Earth Engine qualityMosaic), so that the colours are those of one date
	var RGB_METRICS = 'mean, median, min, max or pN';
	var MOSAICS = ['max', 'min'];

	// composite.reducer
	function reducer(metric) {
		var m = String(metric).trim().toLowerCase();
		var simple = {mean: 'mean', median: 'median', mode: 'mode', min: 'min', max: 'max', sum: 'sum', std: 'stdDev',
			count: 'count'};
		if (simple[m]) return ee.Reducer[simple[m]]();
		var p = /^p(\d+(?:\.\d+)?)$/.exec(m);
		if (p && Number(p[1]) <= 100) return ee.Reducer.percentile([Number(p[1])]);
		throw new Error('unknown metric ' + metric + ': use ' + METRICS);
	}

	// composite.check_metric: error if METRIC is not valid (without Earth Engine)
	function checkMetric(metric) {
		var m = String(metric).trim().toLowerCase();
		if (['mean', 'median', 'mode', 'min', 'max', 'sum', 'std', 'count'].indexOf(m) >= 0) return;
		var p = /^p(\d+(?:\.\d+)?)$/.exec(m);
		if (!(p && Number(p[1]) <= 100)) throw new Error('unknown metric ' + metric + ': use ' + METRICS);
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

	// composite._reduce: image of COL reduced with RED, with the bands BANDS (one, 'value', by default), all masked if
	// COL is empty. With MOSAIC ('max' or 'min'), the bands of the image where the first band is highest or lowest on
	// each pixel instead (the true colour of the date of the maximum or minimum of the variable)
	function reduce(col, red, bands, mosaic) {
		bands = bands || ['value'];
		var empty = ee.Image.constant(bands.length > 1 ? bands.map(function () { return 0; }) : 0).toFloat()
			.rename(bands).updateMask(0);
		var out;
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
		var red = reducer(metric), mos = mosaic(metric, bands);
		if (temporal === 'period') return reduce(col.filter(dateFilter(wins)), red, bands, mos);
		var red2 = reducer(interannual), mos2 = mosaic(interannual, bands);
		if (temporal === 'annual') {
			var years = wins.map(function (w) {
				return reduce(col.filterDate(iso(w[1]), iso(w[2])), red, bands, mos);
			});
			return reduce(ee.ImageCollection.fromImages(years), red2, bands, mos2);
		}
		if (temporal !== 'monthly' && temporal !== '16-day') {
			throw new Error('unknown temporal aggregation ' + temporal + ': use ' + TEMPORAL.join(', '));
		}
		var parts = {};
		wins.forEach(function (w) {
			bins(w, temporal).forEach(function (b) {
				(parts[b[0]] = parts[b[0]] || []).push(reduce(col.filterDate(iso(b[1]), iso(b[2])), red, bands, mos));
			});
		});
		var months = Object.keys(parts).map(Number).sort(function (a, b) { return a - b; }).map(function (m) {
			return reduce(ee.ImageCollection.fromImages(parts[m]), red2, bands, mos2);
		});
		return reduce(ee.ImageCollection.fromImages(months), ee.Reducer.mean(), bands);
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
	var MEASURES = {water: ['NDWI', 'Chl-a', 'NDCI'], snow: ['NDSI', 'SCF'], aerosols: ['ARSL']};
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

	// catalog.THEMES: the themes of the menu, each with its variables (indices) and its own analyses
	function themes() {
		return CATALOG.themes || [];
	}

	// catalog.unit_of: the unit of the values of ENTRY aggregated with METRIC; the sum of a rate per month or per day
	// ('[mm/month]', e.g. the annual precipitation) is a total ('[mm]')
	function unitOf(entry, metric) {
		var m = /^\[(.+)\/(?:month|day)\]$/.exec(entry.unit || '');
		return m && metric === 'sum' ? '[' + m[1] + ']' : entry.unit;
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
	// none (fixed layers, climate, most MODIS products) or the variable compares two periods (RBR: see burnRatio)
	function rgbOf(entry) {
		if (!entry || entry.static || entry.two_periods) return null;
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
	// none for the fixed layers without dates (elevation, slope) and for the cloud frequency
	function fixedFilters(entry) {
		if (entry.static || isCf(entry)) return [];
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
		}}
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

	// Variables (variable.py), for the catalog variables: a spec is {ref, metric, temporal, interannual, period,
	// season, quality} ----------------------------------------------------------------------------------------------

	function spec(options) {
		var s = {metric: 'mean', temporal: 'period', interannual: 'mean', season: null, quality: {}};
		for (var k in options) s[k] = options[k];
		s.quality = withQuality(s.quality);
		var e = s.ref === undefined || s.ref === null ? {} : byRef(s.ref);
		if (e.metric && String(s.metric).trim().toLowerCase() !== e.metric) {  // its only metric (SCF: the mean)
			throw new Error(e.index + ' (' + e.sensor + ") only takes the metric '" + e.metric + "'");
		}
		return s;
	}

	function entryOf(s) {
		return byRef(s.ref);
	}

	function span(s) {
		var wins = windows(s.period, s.season);
		return [iso(wins[0][1]), iso(wins[wins.length - 1][2])];
	}

	// variable.is_static: a variable of the catalog without dates (elevation, slope)
	function isStatic(s) {
		return Boolean(entryOf(s).static);
	}

	// variable.check_dates: error if S is a fixed layer without dates, for WHAT needs them
	function checkDates(s, what) {
		if (!isStatic(s)) return;
		var e = entryOf(s);
		throw new Error(e.index + ' (' + e.sensor + ') is a fixed layer, without dates: it has maps, GeoTIFFs and ' +
			'statistics of the region, but no ' + (what || 'time series, trends or comparisons'));
	}

	// variable._fixed for the fixed layers of the catalog: the mosaic of the tiles of its collection, its terrain (the
	// slope, in degrees), bilinear on pixels RES finer than those of the data and, on pixels RES more than twice as
	// big, the mean of its pixels
	function staticImage(e, res) {
		var img;
		if (e.image_asset) {  // an image (WorldClim), not a collection
			img = ee.Image(e.col).select(e.band);
		} else {
			var col = ee.ImageCollection(e.col).select(e.band);
			img = col.mosaic().setDefaultProjection(col.first().projection());
		}
		img = img.multiply(number(e.scale, 1)).add(number(e.offset, 0));  // e.g. WorldClim, in tenths of a degree
		if (res && res < Number(e.m)) img = img.resample('bilinear');  // variable._resample: pixels finer than the data
		if (e.terrain === 'slope') img = ee.Terrain.slope(img);
		else if (e.terrain === 'aspect') img = ee.Terrain.aspect(img);
		if ((res || Number(e.m)) > 2 * Number(e.m)) img = img.reduceResolution(ee.Reducer.mean(), true, 65535);
		return img.toFloat().rename('value');
	}

	// variable.pin_where: the conditions WHERE with the period START to END for those without a period of their own
	function pinWhere(where, start, end) {
		return (where || []).map(function (c) {
			var out = {};
			for (var k in c) out[k] = c[k];
			if (!out.period && start) out.period = [start, end];
			return out;
		});
	}

	// variable.where_specs: [[spec of its variable, min, max]] of each condition of S.where ({ref, min, max, and
	// optionally metric, temporal, interannual, quality, season, period}): the variable aggregated over the period of
	// S, or its own; the fixed layers have no period
	function whereSpecs(s) {
		return (s.where || []).map(function (c) {
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
						'or filter by other fixed layers (ELEVATION, SLOPE, the BIO variables of WorldClim)');
				}
				cs.period = period.slice();
				cs.metric = c.metric || e.metric || 'mean';
			}
			return [spec(cs), c.min, c.max];
		});
	}

	// variable.mask: the image (1) of the pixels of S that pass its conditions (where), masked elsewhere; null without
	// conditions. A pixel where a condition has no data is left out
	function whereMask(s, region, res) {
		var masks = whereSpecs(s).map(function (w) {
			var value = image(w[0], region, res);
			var m = ee.Image(1).updateMask(value.mask());
			if (w[1] !== null && w[1] !== undefined) m = m.and(value.gte(Number(w[1])));
			if (w[2] !== null && w[2] !== undefined) m = m.and(value.lte(Number(w[2])));
			return m;
		});
		if (!masks.length) return null;
		var out = masks[0];
		masks.slice(1).forEach(function (m) { out = out.and(m); });
		return out.selfMask();
	}

	// variable.check_rgb: error, without Earth Engine, if S has no true colour (see RGB): fixed layers, variables whose
	// images have no red, green and blue bands, and the metrics that do not give colours (see checkRgbMetric). The
	// specs of the app are all of the catalog
	function checkRgb(s) {
		var e = entryOf(s);
		if (e.static) {
			throw new Error(e.index + ' (' + e.sensor + ') is a fixed layer, without dates: it has no images, nor true ' +
				'colour');
		}
		if (!rgbOf(e)) throw noRgb(e);
		checkRgbMetric(s.metric);
		if ((s.temporal || 'period') !== 'period') checkRgbMetric(s.interannual);
	}

	// variable.collection: with the mask of the conditions of S (where) in every image, so the number of pixels and
	// of images of each value count only the pixels kept (with RGB, also the bands red, green and blue of their true
	// colour: see sensorCollection)
	function collection(s, region, res, rgb) {
		if (rgb) checkRgb(s);
		checkDates(s);
		var sp = span(s);
		var col = sensorCollection(entryOf(s), region, sp[0], sp[1], s.quality, rgb);
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
		if (isStatic(s)) {
			var img = staticImage(entryOf(s), res);
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
	var ISLANDS = 'projects/sat-io/open-datasets/shoreline/big_islands';  // areas.ISLANDS
	var WDPA_MAX_ERROR = 10;

	// areas.utm_of
	function utmOf(lon, lat) {
		var zone = Math.min(Math.floor((lon + 180) / 6) + 1, 60);
		return 'EPSG:' + ((lat >= 0 ? 32600 : 32700) + zone);
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

	// areas.region of {admin1: CODE} or {admin2: CODE}: the unit, named by its full name (DISP_EN)
	function adminRegion(level, code) {
		return named(ee.FeatureCollection(GAUL[level]).filter(ee.Filter.eq('GAUL' + level + '_CODE', code)), 'DISP_EN');
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

	// What autoScale and the CRS need, to evaluate once: {area: of the biggest region (m²), centroid: [lon, lat] (for
	// utmOf), total: area of all the regions and boundsArea: of their bounding box (m²)}
	function regionInfo(regions) {
		var geom = regions.geometry();
		return ee.Dictionary({
			area: regions.map(function (f) { return ee.Feature(null, {a: f.geometry().area(1)}); }).aggregate_max('a'),
			centroid: geom.centroid(1000).coordinates(),
			total: geom.area(1000),
			boundsArea: geom.bounds(1000).area(1000)
		});
	}

	// timeseries.auto_scale, from the AREA of the biggest region (m²)
	function autoScale(entry, area) {
		var native = Number(entry.m);
		var need = area ? Math.sqrt(area / TARGET_PIXELS) : native;
		if (need <= native) return native;
		var nice = [];
		for (var e = 1; e <= 5; e++) [1, 2, 5].forEach(function (m) { nice.push(m * Math.pow(10, e)); });
		for (var i = 0; i < nice.length; i++) if (nice[i] >= need) return nice[i];
		return nice[nice.length - 1];
	}

	// timeseries.table: ee.FeatureCollection with a row (region, date, value, n_pixels, n_images) per step of STEPS
	// and region of REGIONS, computed on pixels of SCALE metres in CRS
	function seriesTable(s, regions, metric, stat, scale, steps, crs, tileScale) {
		var col = collection(s, regions.geometry(), scale);
		var red = reducer(metric);
		var sred = reducer(stat).combine(ee.Reducer.count(), '', true);
		var out = ee.String(reducer(stat).getOutputs().get(0));
		var bands = steps.map(function (st, i) { return 's' + i; });
		var img = ee.Image.cat(steps.map(function (st, i) {
			return reduce(col.filterDate(st[0], st[1]), red).rename(bands[i]);
		}));
		var nImages = ee.List(steps.map(function (st) { return col.filterDate(st[0], st[1]).size(); }));
		var stats = img.reduceRegions({collection: regions, reducer: sred, scale: scale, crs: crs,
			tileScale: tileScale || 4});
		var prefix = bands.map(function (b) { return bands.length > 1 ? b + '_' : ''; });
		return stats.map(function (f) {
			f = ee.Feature(f);
			return ee.FeatureCollection(steps.map(function (st, i) {
				return ee.Feature(null, {region: f.get('name'), date: st[0], value: f.get(ee.String(prefix[i]).cat(out)),
					n_pixels: f.get(prefix[i] + 'count'), n_images: nImages.get(i)});
			}));
		}).flatten();
	}

	// timeseries.series (with timeseries._fetch): the rows of STEPS, requested in blocks of at most MAX_ROWS rows,
	// split in two when Earth Engine runs out of memory or time and repeated when it is busy.
	// done(error, rows), progress(done steps, total) after each block.
	function series(s, regions, nRegions, metric, stat, scale, crs, steps, done, progress) {
		var block = Math.max(1, Math.min(Math.floor(MAX_ROWS / Math.max(nRegions, 1)), MAX_STEPS));
		var blocks = [];
		for (var i = 0; i < steps.length; i += block) blocks.push(steps.slice(i, i + block));
		var rows = [];
		var count = 0;

		function fetch(part, attempt, next) {
			seriesTable(s, regions, metric, stat, scale, part, crs).evaluate(function (fc, error) {
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
		var col = collection(s, region);
		var red = reducer(metric || 'mean');
		var imgs = [];
		seasonalBins(s, step).forEach(function (b) {
			if (b[0] !== part) return;
			var value = reduce(col.filterDate(b[2], b[3]), red);
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

	function severityLimits(i) {
		return [SEVERITY[i][1], i + 1 < SEVERITY.length ? SEVERITY[i + 1][1] : null];
	}

	// fire.classify
	function classify(dnbr) {
		var cls = ee.Image.constant(SEVERITY[0][0]);
		SEVERITY.slice(1).forEach(function (c) { cls = cls.add(dnbr.gte(c[1])); });
		return cls.updateMask(dnbr.mask()).toInt8().rename('severity');
	}

	// services.burn_severity: {dnbr, severity, nbr_before, nbr_after (an image with these bands), hectares
	// (ee.FeatureCollection of the regions with the grouped hectares of each class)}
	function burnSeverity(before, after, regions, scale, crs) {
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
	var RBR_COLUMNS = ['region', 'mean', 'median', 'p10', 'p90', 'min', 'max', 'ha'];

	function burnRatio(before, after, regions, scale, crs) {
		var img = comparisonImage(before, after, regions.geometry()).clipToCollection(regions);
		var pre = img.select('reference'), post = img.select('other');
		var dnbr = pre.subtract(post).rename('dnbr');
		var rbr = dnbr.divide(pre.add(RBR_OFFSET)).rename('rbr');  // fire.rbr
		var reducer = ee.Reducer.mean().combine(ee.Reducer.median(), '', true)
			.combine(ee.Reducer.percentile([10, 90]), '', true).combine(ee.Reducer.minMax(), '', true)
			.combine(ee.Reducer.sum(), '', true);
		var stats = rbr.addBands(ee.Image.pixelArea().divide(1e4).updateMask(rbr.mask()).rename('ha')).reduceRegions({
			collection: regions, reducer: reducer, scale: scale, crs: crs, tileScale: 4});
		return {image: ee.Image.cat([rbr, dnbr, pre, post]).rename(['rbr', 'dnbr', 'nbr_before', 'nbr_after']),
			stats: stats};
	}

	// the rows of services._rbr from the features of the statistics of burnRatio
	function rbrTable(features) {
		return features.map(function (f) {
			var p = f.properties;
			return {region: String(p.name), mean: p.rbr_mean, median: p.rbr_median, p10: p.rbr_p10, p90: p.rbr_p90,
				min: p.rbr_min, max: p.rbr_max, ha: p.ha_sum || 0};
		});
	}

	// fire.table: rows of every class of a region from the GROUPS of the grouped sum of hectares
	function severityTable(groups, region, lang) {
		var ha = {};
		(groups || []).forEach(function (g) { ha[Math.round(g['class'])] = g.sum; });
		return SEVERITY.map(function (c, i) {
			var lim = severityLimits(i);
			return {region: region, 'class': c[0], label: lang === 'en' ? c[3] : c[2], dnbr_min: lim[0], dnbr_max: lim[1],
				ha: ha[c[0]] || 0};
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

	return {
		CATALOG: CATALOG, variables: variables, byRef: byRef, number: number, unitOf: unitOf, themes: themes,
		iso: iso, date: date, windows: windows, bins: bins, reducer: reducer, composite: composite, TEMPORAL: TEMPORAL,
		QUALITY: QUALITY, FILTERS: FILTERS, MEASURES: MEASURES, filters: filters, fixedFilters: fixedFilters,
		conflicts: conflicts,
		sensorCollection: sensorCollection, spec: spec, entryOf: entryOf, isStatic: isStatic, checkDates: checkDates,
		collection: collection, image: image, pinWhere: pinWhere, whereSpecs: whereSpecs, whereMask: whereMask,
		utmOf: utmOf, findProtectedAreas: findProtectedAreas, wdpaGeometries: wdpaGeometries, wdpaRegion: wdpaRegion,
		ecoregionAt: ecoregionAt, bboxRegion: bboxRegion, findAdminUnits: findAdminUnits, adminRegion: adminRegion,
		islandAt: islandAt,
		STEPS: STEPS, seriesBins: seriesBins, dailyDays: dailyDays, dailyBins: dailyBins, regionInfo: regionInfo,
		autoScale: autoScale, seriesTable: seriesTable, series: series,
		TREND_STEPS: TREND_STEPS, OUTPUTS: OUTPUTS, parts: parts, partKey: partKey, partLabel: partLabel,
		seasonalBins: seasonalBins, trendImage: trendImage, trendVis: trendVis, erfc: erfc, mannKendall: mannKendall,
		sen: sen, trendRows: trendRows, withParts: withParts, profile: profile, comparisonImage: comparisonImage,
		DIVERGING: DIVERGING, SEVERITY: SEVERITY, SEVERITY_COLOURS: SEVERITY_COLOURS, BURNED: BURNED,
		classify: classify, burnSeverity: burnSeverity, severityTable: severityTable, RBR_OFFSET: RBR_OFFSET,
		RBR_COLUMNS: RBR_COLUMNS, burnRatio: burnRatio, rbrTable: rbrTable,
		ramp: ramp, percentiles: percentiles, visParams: visParams,
		RGB: RGB, RGB_BANDS: RGB_BANDS, RGB_METRICS: RGB_METRICS, RGB_STRETCH: RGB_STRETCH, RGB_RANGE: RGB_RANGE,
		rgbOf: rgbOf, withRgb: withRgb, checkMetric: checkMetric, checkRgbMetric: checkRgbMetric, checkRgb: checkRgb,
		mosaic: mosaic, rgbPercentiles: rgbPercentiles, rgbVis: rgbVis
	};
})();
