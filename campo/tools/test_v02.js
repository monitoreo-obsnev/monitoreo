// Prueba en Node, contra Earth Engine, lo que la versión 0.2.0 de la app añade con el núcleo de MonitorEO 0.3.81:
// corrección topográfica de Landsat, nieve por NDSI, los tests de tendencia, la fuente de los datos y la capa.
//   node tools/test_v02.js <carpeta con node_modules/@google/earthengine> token.json
var fs = require('fs'), path = require('path'), vm = require('vm');
var ee = require(path.join(process.argv[2], 'node_modules', '@google', 'earthengine'));
var tok = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
global.ee = ee;
var LIB = path.join(__dirname, '..', 'app', 'src', 'main', 'assets', 'www', 'lib');
vm.runInThisContext(fs.readFileSync(path.join(LIB, 'catalog.js'), 'utf8') + '\nglobal.CATALOG = CATALOG;');
vm.runInThisContext(fs.readFileSync(path.join(LIB, 'core.js'), 'utf8') + '\nglobal.MonitorEO = MonitorEO;');
var mo = MonitorEO;

var P = {id: 'hoya', lat: 37.0944, lon: -3.3858}, R = 100;
function region() { return ee.FeatureCollection([ee.Feature(ee.Geometry.Point([P.lon, P.lat]).buffer(R), {name: P.id})]); }
function evaluate(o) { return new Promise(function (res, rej) { o.evaluate(function (v, e) { e ? rej(new Error(e)) : res(v); }); }); }
function seriesP(s, metric, scale, crs, steps) {
  return new Promise(function (res, rej) { mo.series(s, region(), 1, metric, 'mean', scale, crs, steps, function (e, rows) { e ? rej(new Error(e)) : res(rows); }); });
}
function value(opts, scale) {
  var s = mo.spec(opts), g = region().geometry();
  return evaluate(mo.image(s, g, scale).reduceRegion({reducer: ee.Reducer.mean(), geometry: g, scale: scale,
    crs: mo.utmOf(P.lon, P.lat)})).then(function (v) { return v.value; });
}

ee.data.setAuthToken(null, 'Bearer', tok.access_token, tok.expires_in, [], function () {
  ee.initialize(null, null, async function () {
    var t0 = Date.now(), crs = mo.utmOf(P.lon, P.lat), per = ['2025-06-01', '2025-08-31'];
    console.log('versión', mo.CATALOG.about.version);
    console.log('fuente NDVI S2', mo.dataSource(mo.byRef(27), [per]));
    console.log('noTopographic NDVI S2 →', mo.noTopographic(mo.byRef(27)));
    console.log('noTopographic NDVI Landsat →', mo.noTopographic(mo.byRef(24)));
    console.log('manual NDVI →', (mo.wikiSection('NDVI', 'es') || {}).url);
    var a = await value({ref: 24, period: per, metric: 'mean'}, 30);
    var b = await value({ref: 24, period: per, metric: 'mean', quality: {topographic: true}}, 30);
    console.log('NDVI Landsat verano 2025, sin / con corrección topográfica:', a, b);
    var c = await value({ref: 27, period: ['2025-03-01', '2025-05-31'], metric: 'mean'}, 10);
    var d = await value({ref: 27, period: ['2025-03-01', '2025-05-31'], metric: 'mean', quality: {snow_ndsi: mo.SNOW_NDSI_DEFAULT}}, 10);
    console.log('NDVI S2 primavera 2025, filtro de nieve normal / con NDSI ≥ 0,4:', c, d);
    var s = mo.spec({ref: 27, period: ['2017-01-01', '2025-12-31'], metric: 'mean', season: ['06-01', '09-30']});
    var sb = mo.seasonalBins(s, 'annual');
    var rows = await seriesP(s, 'mean', 10, crs, sb.map(function (x) { return [x[2], x[3]]; }));
    var yearly = mo.withParts(rows, sb), first = mo.windows(s.period, s.season)[0][0];
    mo.TREND_TESTS.forEach(function (t) {
      var r = mo.trendRows(yearly, 'annual', first, 'es', undefined, undefined, t)[0];
      console.log('tendencia', t, JSON.stringify({n: r.n, tau: r.tau, p: r.p_value, sig: r.significant, sen: r.slope}));
    });
    var area = ee.Geometry.Point([P.lon, P.lat]).buffer(3000);
    var img = mo.image(mo.spec({ref: 27, period: per, metric: 'mean'}), area).clip(area);
    var st = await evaluate(mo.percentiles(img, area, 30));
    var vis = mo.visParams(st, mo.rampEntry(mo.byRef(27), 'mean', 'period'));
    console.log('capa: percentiles', JSON.stringify(st), '→', vis.min, vis.max);
    console.log('total', Math.round((Date.now() - t0) / 1000), 's');
  }, function (e) { console.error('init', e); }, null, tok.project);
}, false);
