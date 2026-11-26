// Prueba en Node, contra Earth Engine, la capa que la app guarda para verla sin conexión (app.js, $('an-layer')):
// percentiles → visParams → PNG en Web Mercator sobre la caja del punto.
//   node tools/test_layer.js <carpeta con node_modules/@google/earthengine> token.json salida.png [ref inicio fin métrica px]
// px: lado de la imagen; por omisión el de la app (el píxel de la variable, como mucho 900)
var fs = require('fs'), path = require('path'), vm = require('vm');
var ee = require(path.join(process.argv[2], 'node_modules', '@google', 'earthengine'));
var tok = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
global.ee = ee;
var LIB = path.join(__dirname, '..', 'app', 'src', 'main', 'assets', 'www', 'lib');
vm.runInThisContext(fs.readFileSync(path.join(LIB, 'catalog.js'), 'utf8') + '\nglobal.CATALOG = CATALOG;');
vm.runInThisContext(fs.readFileSync(path.join(LIB, 'core.js'), 'utf8') + '\nglobal.MonitorEO = MonitorEO;');
var mo = MonitorEO;

var P = {lat: 37.0944, lon: -3.3858}, R = 3000;
var REF = Number(process.argv[5] || 27), START = process.argv[6] || '2025-06-01', END = process.argv[7] || '2025-08-31';
var METRIC = process.argv[8] || 'median';
var PX = Number(process.argv[9]) || Math.max(16, Math.min(900, Math.ceil(2 * (R + 50) / Math.max(Number(mo.byRef(REF).m) || 10, 10))));
var dlat = (R + 50) / 111320, dlon = dlat / Math.cos(P.lat * Math.PI / 180);
var box = [P.lat - dlat, P.lon - dlon, P.lat + dlat, P.lon + dlon];

ee.data.setAuthToken(null, 'Bearer', tok.access_token, tok.expires_in, [], function () {
  ee.initialize(null, null, function () {
    var t0 = Date.now(), e = mo.byRef(REF);
    var area = ee.Geometry.Point([P.lon, P.lat]).buffer(R);
    var img = mo.image(mo.spec({ref: REF, period: [START, END], metric: METRIC}), area, undefined).clip(area);
    mo.percentiles(img, area, Math.max(Number(e.m), 30)).evaluate(function (stats, err) {
      if (err) return console.error(err);
      var vis = mo.visParams(stats, mo.rampEntry(e, METRIC, 'period'));
      console.log(e.index, e.sensor, e.m + ' m', START, END, METRIC, PX + ' px'); console.log('vis', vis.min, vis.max, vis.palette.length, 'colores');
      img.visualize(vis).getThumbURL({region: ee.Geometry.Rectangle([box[1], box[0], box[3], box[2]], null, false),
        dimensions: PX, format: 'png', crs: 'EPSG:3857'}, function (url, error) {
        if (error) return console.error(error);
        fetch(url).then(function (r) { console.log('HTTP', r.status, r.headers.get('content-type')); return r.arrayBuffer(); })
          .then(function (buf) {
            var b = Buffer.from(buf);
            fs.writeFileSync(process.argv[4], b);
            console.log('PNG', b.length, 'bytes,', b.readUInt32BE(16), 'x', b.readUInt32BE(20), 'px,', Math.round((Date.now() - t0) / 1000), 's');
          });
      });
    });
  }, function (e) { console.error('init', e); }, null, tok.project);
}, false);
