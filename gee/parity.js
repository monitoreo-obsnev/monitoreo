// Runs cases with the core of the app (catalog.js and core.js) in Node, for tests/test_gee.py, which runs the same
// cases with the Python package: reads the cases (JSON) from stdin and writes their results (JSON) to stdout.
// Earth Engine: an access token in EE_ACCESS_TOKEN and the project in EE_PROJECT.

var fs = require('fs');
var path = require('path');
var vm = require('vm');

global.ee = require('@google/earthengine');
['catalog.js', 'core.js'].forEach(function (f) {
	vm.runInThisContext(fs.readFileSync(path.join(__dirname, f), 'utf8'), {filename: f});
});
var mo = global.MonitorEO;

function regionOf(r, done) {
	if (r.bbox) return done(null, mo.bboxRegion(r.bbox));
	if (r.geojson) {
		return done(null, ee.FeatureCollection(r.geojson.features.map(function (f) {
			return ee.Feature(ee.Geometry(f.geometry), {name: f.properties.name});
		})));
	}
	mo.wdpaGeometries([r.wdpa_id]).evaluate(function (info, error) {
		if (error) return done(error);
		done(null, mo.wdpaRegion(info));
	});
}

// The spec of the case C: a variable of the catalog (ref) or, with custom ({asset, band, use, scale, offset, unit,
// terrain}), data of Earth Engine by its ID, whose entry (mo.customEntry) needs the type of the asset and the pixel
// size of the band (mo.assetInfo, as variable.native_scale): done(error), with C.spec carrying that entry
function prepare(c, done) {
	var custom = c.spec.custom;
	if (!custom) return done(null);
	mo.assetInfo(custom.asset, function (error, info) {
		if (error) return done(error);
		var s = {};
		for (var k in c.spec) if (k !== 'custom') s[k] = c.spec[k];
		try {
			s.entry = mo.customEntry({asset: info.asset, type: info.type, dated: info.dated, band: custom.band,
				use: custom.use, m: info.scales[custom.band], scale: custom.scale, offset: custom.offset, unit: custom.unit,
				terrain: custom.terrain});
		} catch (e) {
			return done(e);
		}
		c.spec = s;
		done(null);
	});
}

// Scale, CRS and number of the regions, as the Python package chooses them
function setup(entry, regions, done) {
	ee.Dictionary({info: mo.regionInfo(regions), n: regions.size()}).evaluate(function (d, error) {
		if (error) return done(error);
		var c = d.info.centroid;
		done(null, {scale: mo.autoScale(entry, d.info.area), crs: mo.utmOf(c[0], c[1]), n: d.n});
	});
}

function seasonalRows(s, regions, step, metric, stat, scale, crs, n, done) {
	var sbins = mo.seasonalBins(s, step);
	mo.series(s, regions, n, metric, stat, scale, crs, sbins.map(function (b) { return [b[2], b[3]]; }),
		function (error, rows) {
			if (error) return done(error);
			done(null, mo.withParts(rows, sbins));
		});
}

var CASES = {
	series: function (c, regions, done) {
		var s = mo.spec(c.spec), entry = mo.entryOf(s);
		setup(entry, regions, function (error, g) {
			if (error) return done(error);
			function run(steps) {
				mo.series(s, regions, g.n, c.metric, c.stat, g.scale, g.crs, steps, function (err, rows) {
					done(err, {rows: rows, scale: g.scale});
				});
			}
			if (c.step !== 'daily') return run(mo.seriesBins(s, c.step));
			mo.dailyDays(s, regions.geometry()).evaluate(function (days, err) {
				if (err) return done(err);
				run(mo.dailyBins(days));
			});
		});
	},
	trends: function (c, regions, done) {
		var s = mo.spec(c.spec), entry = mo.entryOf(s);
		setup(entry, regions, function (error, g) {
			if (error) return done(error);
			seasonalRows(s, regions, c.step, c.metric, c.stat, g.scale, g.crs, g.n, function (err, yearly) {
				if (err) return done(err);
				done(null, {rows: mo.trendRows(yearly, c.step, mo.windows(s.period, s.season)[0][0], 'en'), yearly: yearly});
			});
		});
	},
	compare: function (c, regions, done) {
		var ref = mo.spec(c.spec), other = mo.spec(c.spec);
		other.period = c.other;
		other.where = mo.pinWhere(ref.where, ref.period[0], ref.period[1]);  // services.same_area
		setup(mo.entryOf(ref), regions, function (error, g) {
			if (error) return done(error);
			seasonalRows(ref, regions, c.step, c.metric, c.stat, g.scale, g.crs, g.n, function (e1, a) {
				if (e1) return done(e1);
				seasonalRows(other, regions, c.step, c.metric, c.stat, g.scale, g.crs, g.n, function (e2, b) {
					done(e2, e2 ? null : {profile: mo.profile(a, b)});
				});
			});
		});
	},
	percentiles: function (c, regions, done) {
		var s = mo.spec(c.spec), geom = regions.geometry();
		var img = c.difference ? (function () {
			var other = mo.spec(c.spec);
			other.period = c.difference;
			other.where = mo.pinWhere(s.where, s.period[0], s.period[1]);  // services.same_area
			return mo.comparisonImage(s, other, geom).select('difference');
		})() : mo.image(s, geom);
		mo.percentiles(img.clipToCollection(regions), geom, Number(mo.entryOf(s).m)).evaluate(function (st, error) {
			done(error, st);
		});
	},
	// the true colour of the images of a variable (services.rgb_map): the percentiles 2 and 98 of its bands
	rgb_percentiles: function (c, regions, done) {
		var s = mo.spec(c.spec), geom = regions.geometry();
		var img = mo.image(s, geom, null, true).clipToCollection(regions);
		mo.rgbPercentiles(img, geom, Number(mo.entryOf(s).m)).evaluate(function (st, error) {
			done(error, st);
		});
	},
	trend_image: function (c, regions, done) {
		var s = mo.spec(c.spec), geom = regions.geometry();
		mo.trendImage(s, geom, c.step, c.part, c.metric).reduceRegion({reducer: ee.Reducer.mean(), geometry: geom,
			scale: Number(mo.entryOf(s).m), bestEffort: true}).evaluate(function (st, error) { done(error, st); });
	},
	burn: function (c, regions, done) {
		var before = mo.spec(c.spec), after = mo.spec(c.spec);
		after.period = c.after;
		var entry = mo.entryOf(before);
		setup(entry, regions, function (error, g) {
			if (error) return done(error);
			mo.burnSeverity(before, after, regions, Number(entry.m), g.crs).hectares.evaluate(function (fc, err) {
				if (err) return done(err);
				var rows = [];
				fc.features.forEach(function (f) {
					rows = rows.concat(mo.severityTable(f.properties.groups, String(f.properties.name), 'en'));
				});
				done(null, {classes: rows});
			});
		});
	},
	burn_rbr: function (c, regions, done) {
		var before = mo.spec(c.spec), after = mo.spec(c.spec);
		after.period = c.after;
		var entry = mo.entryOf(before);
		setup(entry, regions, function (error, g) {
			if (error) return done(error);
			mo.burnRatio(before, after, regions, Number(entry.m), g.crs).stats.evaluate(function (fc, err) {
				if (err) return done(err);
				done(null, {stats: mo.rbrTable(fc.features)});
			});
		});
	},
	// the RdNBR of Miller & Thode 2007 (services._rdnbr), of the entry of the spec (Sentinel-2, Landsat, MODIS Terra
	// or Aqua): the hectares of its classes, the changed area and the statistics of the RdNBR of each region
	burn_rdnbr: function (c, regions, done) {
		var before = mo.spec(c.spec), after = mo.spec(c.spec);
		after.period = c.after;
		var entry = mo.entryOf(before);
		setup(entry, regions, function (error, g) {
			if (error) return done(error);
			var out = mo.burnSeverity(before, after, regions, Number(entry.m), g.crs, 'RdNBR');
			ee.Dictionary({hectares: out.hectares, stats: out.stats}).evaluate(function (d, err) {
				if (err) return done(err);
				var rows = [];
				d.hectares.features.forEach(function (f) {
					rows = rows.concat(mo.severityTable(f.properties.groups, String(f.properties.name), 'en', 'RdNBR'));
				});
				done(null, {classes: rows, burned_ha: mo.burnedHa(rows), stats: mo.rdnbrTable(d.stats.features)});
			});
		});
	}
};

function main(cases) {
	var results = {};
	var names = Object.keys(cases);
	function next(i) {
		if (i === names.length) {
			process.stdout.write(JSON.stringify(results));
			return;
		}
		var c = cases[names[i]];
		regionOf(c.region, function (error, regions) {
			if (error) {
				results[names[i]] = {error: String(error)};
				return next(i + 1);
			}
			prepare(c, function (err) {
				if (err) {
					results[names[i]] = {error: String(err)};
					return next(i + 1);
				}
				try {
					CASES[c.kind](c, regions, function (e, out) {
						results[names[i]] = e ? {error: String(e)} : out;
						next(i + 1);
					});
				} catch (e) {
					results[names[i]] = {error: String(e.stack || e)};
					next(i + 1);
				}
			});
		});
	}
	next(0);
}

var input = fs.readFileSync(0, 'utf8');
ee.data.setAuthToken(null, 'Bearer', process.env.EE_ACCESS_TOKEN, 3600, [], function () {
	ee.initialize(null, null, function () { main(JSON.parse(input)); }, function (e) {
		process.stderr.write('cannot connect to Earth Engine: ' + e + '\n');
		process.exit(1);
	}, null, process.env.EE_PROJECT);
}, false);
