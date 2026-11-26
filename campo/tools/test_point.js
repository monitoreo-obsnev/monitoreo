// Prueba en Node, contra Earth Engine, las llamadas de core.js que hace la app en un punto (ficha, valor, serie,
// tendencia, capa): node tools/test_point.js NPM_EE_DIR token.json
var fs = require('fs'), path = require('path'), vm = require('vm');
var ee = require(path.join(process.argv[2], 'node_modules', '@google', 'earthengine'));
var tok = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
global.ee = ee;
var LIB = path.join(__dirname, '..', 'app', 'src', 'main', 'assets', 'www', 'lib');
vm.runInThisContext(fs.readFileSync(path.join(LIB, 'catalog.js'), 'utf8') + '\nglobal.CATALOG = CATALOG;');
vm.runInThisContext(fs.readFileSync(path.join(LIB, 'core.js'), 'utf8') + '\nglobal.MonitorEO = MonitorEO;');
var mo = MonitorEO;

var P = {id: 'hoya', lat: 37.0944, lon: -3.3858};
function regionOf(pts, r) {
  return ee.FeatureCollection(pts.map(function (p) {
    var g = ee.Geometry.Point([p.lon, p.lat]);
    return ee.Feature(r > 0 ? g.buffer(r) : g, {name: p.id});
  }));
}
function scaleOf(e, r) { return mo.autoScale(e, r > 0 ? Math.PI * r * r : 0); }
function evaluate(o) { return new Promise(function (res, rej) { o.evaluate(function (v, e) { e ? rej(new Error(e)) : res(v); }); }); }
function seriesP(s, fc, metric, scale, crs, steps) {
  return new Promise(function (res, rej) { mo.series(s, fc, 1, metric, 'mean', scale, crs, steps, function (e, rows) { e ? rej(new Error(e)) : res(rows); }); });
}
function daysAgo(n) { return new Date(Date.now() - n * 864e5).toISOString().slice(0, 10); }

ee.data.setAuthToken(null, 'Bearer', tok.access_token, tok.expires_in, [], function () {
  ee.initialize(null, null, async function () {
    var crs = mo.utmOf(P.lon, P.lat), t0 = Date.now();
    console.log('crs', crs);
    // Ficha (como computeFicha)
    var F = [{ref: 27, days: 60, metric: 'median'}, {ref: 14, days: 90, metric: 'mean'}, {ref: 112, y: true, metric: 'sum'}, {ref: 106}, {ref: 107}];
    for (var f of F) {
      var e = mo.byRef(f.ref), r = 100, scale = scaleOf(e, r), opts = {ref: f.ref};
      if (f.days) { opts.period = [daysAgo(f.days), daysAgo(0)]; opts.metric = f.metric; }
      if (f.y) { opts.period = ['2025-01-01', '2025-12-31']; opts.metric = f.metric; }
      var s = mo.spec(opts), fc = regionOf([P], r);
      var rows = mo.image(s, fc.geometry(), scale).reduceRegions({collection: fc,
        reducer: ee.Reducer.mean().combine(ee.Reducer.count(), '', true), scale: scale, crs: crs, tileScale: 4})
        .map(function (ft) { return ee.Feature(null, {id: ft.get('name'), mean: ft.get('mean'), count: ft.get('count')}); });
      var v = await evaluate(rows);
      console.log('ficha', e.index, e.sensor, 'scale', scale, JSON.stringify(v.features[0].properties), mo.unitOf(e, f.metric || 'mean'));
    }
    // Valor del periodo, píxel del punto
    var s1 = mo.spec({ref: 27, period: ['2025-06-01', '2025-08-31'], metric: 'mean'});
    var g = regionOf([P], 0).geometry();
    var red = ee.Reducer.mean().combine(ee.Reducer.stdDev(), '', true).combine(ee.Reducer.minMax(), '', true).combine(ee.Reducer.count(), '', true);
    var val = await evaluate(ee.Dictionary({stats: mo.image(s1, g, 10).reduceRegion({reducer: red, geometry: g, scale: 10, crs: crs}),
      images: mo.collection(s1, g, 10).size()}));
    console.log('valor', JSON.stringify(val));
    // Serie mensual
    var s2 = mo.spec({ref: 27, period: ['2024-01-01', '2025-12-31'], metric: 'mean'});
    var rows2 = await seriesP(s2, regionOf([P], 100), 'mean', 10, crs, mo.seriesBins(s2, 'monthly'));
    console.log('serie', rows2.length, 'pasos; ej.', JSON.stringify(rows2.slice(5, 8)));
    // Tendencia anual, temporada de verano
    var s3 = mo.spec({ref: 27, period: ['2017-01-01', '2025-12-31'], metric: 'mean', season: ['06-01', '09-30']});
    var sb = mo.seasonalBins(s3, 'annual');
    var rows3 = await seriesP(s3, regionOf([P], 100), 'mean', 10, crs, sb.map(function (b) { return [b[2], b[3]]; }));
    var yearly = mo.withParts(rows3, sb);
    console.log('tendencia', JSON.stringify(mo.trendRows(yearly, 'annual', mo.windows(s3.period, s3.season)[0][0], 'es')[0]));
    // Capa
    var area = ee.Geometry.Point([P.lon, P.lat]).buffer(3000);
    var img = mo.image(s1, area).clip(area);
    var st = await evaluate(mo.percentiles(img, area, 30));
    var vis = mo.visParams(st, mo.rampEntry(mo.byRef(27), 'mean', 'period'));
    img.getMapId(vis, function (m, err) {
      console.log('capa', err || m.urlFormat.replace(/maps\/[^/]+/, 'maps/…'), JSON.stringify({min: vis.min, max: vis.max}));
      console.log('total', Math.round((Date.now() - t0) / 1000), 's');
    });
  }, function (e) { console.error('init', e); }, null, tok.project);
}, false);
