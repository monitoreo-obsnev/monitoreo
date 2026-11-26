/*
 * MonitorEO Campo: points of a field trip and the variables of MonitorEO computed in Earth Engine at them.
 *
 * The computation is that of MonitorEO itself: lib/core.js and lib/catalog.js of monitoreo/gee, unchanged (global
 * MonitorEO). This file is only the interface, the account, the points and the results kept on the phone.
 * window.Android (MainActivity.java) gives the token, HTTP without CORS, the GPS and the files.
 */
(function () {
  'use strict';

  var mo = MonitorEO;
  var BROKER = 'https://monitoreo-broker-872770286973.europe-west1.run.app';  // monitoreo.services.BROKER
  var MAX_STEPS = 400;  // ui.js LIMITS.maxSteps
  var FICHA = [  // the quick card: {ref, days back from today | 'lastYear', metric}
    {ref: 27, days: 60, metric: 'median'},   // NDVI Sentinel-2
    {ref: 23, days: 60, metric: 'median'},   // EVI Sentinel-2
    {ref: 10, days: 60, metric: 'median'},   // NDWI Sentinel-2
    {ref: 8, days: 60, metric: 'median'},    // NDSI Sentinel-2
    {ref: 14, days: 90, metric: 'mean'},     // LST Landsat
    {ref: 112, period: 'lastYear', metric: 'sum'},  // precipitation ERA5-Land: total of the last complete year
    {ref: 106}, {ref: 107}                   // elevation, slope (Copernicus DEM)
  ];

  // Helpers --------------------------------------------------------------------------------------------------------

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  function iso(d) { return d.toISOString().slice(0, 10); }
  function daysAgo(n) { return iso(new Date(Date.now() - n * 86400000)); }
  function num(v, digits) {
    if (v === null || v === undefined || isNaN(v)) return '—';
    v = Number(v);
    if (digits !== undefined) return v.toFixed(digits);
    var a = Math.abs(v);
    return a >= 1000 ? v.toFixed(0) : a >= 100 ? v.toFixed(1) : a >= 10 ? v.toFixed(2) : v.toFixed(3);
  }
  function dec(s) { return i18n.lang === 'es' ? String(s).replace('.', ',') : String(s); }  // the decimal mark of the language
  function unitText(e, metric) {
    var u = String(mo.unitOf(e, metric) || '').replace(/^\[|\]$/g, '');
    return u === 'unitless' ? '' : u;
  }
  function toast(text, ms) {
    var t = $('toast');
    t.textContent = text;
    t.classList.remove('hidden');
    clearTimeout(toast.timer);
    toast.timer = setTimeout(function () { t.classList.add('hidden'); }, ms || 3000);
  }
  function errText(e) { return i18n.tr((e && e.message) || String(e)); }

  // Settings and points (localStorage); results (IndexedDB) --------------------------------------------------------

  function load(key, def) {
    try { var v = localStorage.getItem(key); return v ? JSON.parse(v) : def; } catch (e) { return def; }
  }
  function store(key, v) {
    try { localStorage.setItem(key, JSON.stringify(v)); } catch (e) { toast(t('No se pudo guardar: {0}', errText(e))); }
  }

  var S = load('campo.settings', {});
  if (!S.mode) S.mode = 'shared';
  if (!S.lastRef) { S.lastRef = 27; S.lastTheme = 'vegetation'; }  // NDVI Sentinel-2
  if (!/^mo-[0-9a-f]{16}$/.test(S.userId || '')) {  // services.user_id: anonymous ID of this installation
    var b = new Uint8Array(8);
    crypto.getRandomValues(b);
    S.userId = 'mo-' + Array.prototype.map.call(b, function (x) { return ('0' + x.toString(16)).slice(-2); }).join('');
  }
  function saveSettings() { store('campo.settings', S); }
  saveSettings();

  var points = load('campo.points', []);
  function savePoints() { store('campo.points', points); }
  function pointById(id) { return points.filter(function (p) { return p.id === id; })[0]; }
  function newId() { return 'p' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6); }

  var dbp = new Promise(function (resolve, reject) {
    var r = indexedDB.open('campo', 2);
    r.onupgradeneeded = function (ev) {
      var db = r.result;
      if (ev.oldVersion < 1) db.createObjectStore('results', {keyPath: 'id'}).createIndex('point', 'point');
      if (ev.oldVersion < 2) {
        db.createObjectStore('tiles', {keyPath: 'k'});   // {k: 'sat/z/x/y', b: Blob} of the base maps kept offline
        db.createObjectStore('areas', {keyPath: 'id'});  // the areas downloaded (their tiles follow from bounds and zooms)
      }
    };
    r.onsuccess = function () { resolve(r.result); };
    r.onerror = function () { reject(r.error); };
  });
  function tx(mode, f, storeName) {
    storeName = storeName || 'results';
    return dbp.then(function (db) {
      return new Promise(function (resolve, reject) {
        var t = db.transaction(storeName, mode);
        var out = f(t.objectStore(storeName));
        t.oncomplete = function () { resolve(out && out.result !== undefined ? out.result : out); };
        t.onerror = function () { reject(t.error); };
      });
    });
  }
  function saveResult(r) { return tx('readwrite', function (os) { os.put(r); }); }
  function resultsOf(pointId) {
    return tx('readonly', function (os) { return os.index('point').getAll(pointId); });
  }
  function deleteResult(id) { return tx('readwrite', function (os) { os.delete(id); }); }
  function deleteResultsOf(pointId) {
    return resultsOf(pointId).then(function (rs) {
      return tx('readwrite', function (os) { rs.forEach(function (r) { os.delete(r.id); }); });
    });
  }

  // The bridge with Android ----------------------------------------------------------------------------------------

  var calls = {}, seq = 0;
  window.AndroidCallback = function (id, json) {
    var c = calls[id];
    if (!c) return;
    delete calls[id];
    var v;
    try { v = JSON.parse(json); } catch (e) { v = {error: json}; }
    if (v && v.error) c.reject(new Error(v.error)); else c.resolve(v);
  };
  function native(method, arg) {
    if (!window.Android) return Promise.reject(new Error(t('solo disponible en el teléfono')));
    return new Promise(function (resolve, reject) {
      var id = 'c' + (++seq);
      calls[id] = {resolve: resolve, reject: reject};
      window.Android.call(id, method, arg == null ? '' : typeof arg === 'string' ? arg : JSON.stringify(arg));
    });
  }
  function httpJson(url) {
    if (!window.Android) return fetch(url).then(function (r) { return r.json().then(function (d) { return {status: r.status, data: d}; }); });
    return native('http', {url: url}).then(function (r) {
      var d;
      try { d = JSON.parse(r.body); } catch (e) { d = {error: r.body || ('HTTP ' + r.status)}; }
      return {status: r.status, data: d};
    });
  }
  function broker() { return (S.broker || BROKER).replace(/\/$/, ''); }

  // Earth Engine ---------------------------------------------------------------------------------------------------

  // {token, expires (s), project} of the account chosen
  function getToken() {
    if (S.mode === 'sa') {
      return native('serviceAccountToken').then(function (t) {
        return {token: t.access_token, expires: t.expires_in, project: S.project || t.project};
      });
    }
    return httpJson(broker() + '/token?user=' + S.userId).then(function (r) {
      if (r.status !== 200) {
        var e = new Error(r.data.error || ('broker ' + r.status));
        if (r.data.code === 'spent' || r.data.code === 'project') {
          e.message = t('{0}. Mientras tanto, usa tu cuenta de servicio (Ajustes).', i18n.tr(e.message));
        }
        throw e;
      }
      return {token: r.data.access_token, expires: Math.max(60, r.data.expires_at - Date.now() / 1000),
        project: r.data.project};
    });
  }

  var connecting = null, connectedMode = null;
  function connect() {
    if (connecting && connectedMode === S.mode + '|' + (S.project || '')) return connecting;
    if (!navigator.onLine) return Promise.reject(new Error(t('sin conexión: puedes ver los resultados guardados')));
    connectedMode = S.mode + '|' + (S.project || '');
    try { ee.reset(); } catch (e) { /* first time */ }
    connecting = getToken().then(function (t) {
      return new Promise(function (resolve, reject) {
        ee.data.setAuthToken(null, 'Bearer', t.token, t.expires, [], function () {
          ee.data.setAuthTokenRefresher(function (args, cb) {
            getToken().then(function (n) {
              cb({access_token: n.token, token_type: 'Bearer', expires_in: n.expires});
            }, function (e) { cb({error: errText(e)}); });
          });
          ee.initialize(null, null, function () {
            if (S.mode === 'shared' && ee.data.setDefaultWorkloadTag) ee.data.setDefaultWorkloadTag(S.userId);
            else if (ee.data.resetWorkloadTag) ee.data.resetWorkloadTag(true);
            resolve(t.project);
          }, function (e) { reject(new Error(String(e))); }, null, t.project);
        }, false);
      });
    });
    connecting.catch(function () { connecting = null; });
    return connecting;
  }

  function evaluate(obj) {
    return new Promise(function (resolve, reject) {
      obj.evaluate(function (v, error) { if (error) reject(new Error(error)); else resolve(v); });
    });
  }

  // A point as the region of MonitorEO: a feature named by its id, the point itself or a circle of RADIUS m
  function regionOf(pts, radius) {
    return ee.FeatureCollection(pts.map(function (p) {
      var g = ee.Geometry.Point([p.lon, p.lat]);
      return ee.Feature(radius > 0 ? g.buffer(radius) : g, {name: p.id});
    }));
  }
  // The radius used for E: the pixel of the point when the pixels of E are bigger than the circle (a circle smaller
  // than a pixel holds no pixel centre, and Earth Engine would give no value)
  function radiusFor(e, radius) { return Number(e.m) > radius ? 0 : radius; }
  function scaleOf(e, radius) { return mo.autoScale(e, radius > 0 ? Math.PI * radius * radius : 0); }

  // Map --------------------------------------------------------------------------------------------------------------

  // The base maps read their tiles first from the phone (the areas downloaded for offline use), then from the network
  var CachedTiles = L.TileLayer.extend({
    createTile: function (coords, done) {
      var img = document.createElement('img'), layer = this;
      img.alt = '';
      img.onload = function () { if (img._blob) URL.revokeObjectURL(img.src); done(null, img); };
      img.onerror = function (e) { done(e, img); };
      tileGet(this.options.id + '/' + coords.z + '/' + coords.x + '/' + coords.y).then(function (blob) {
        if (blob) { img._blob = true; img.src = URL.createObjectURL(blob); } else img.src = layer.getTileUrl(coords);
      }, function () { img.src = layer.getTileUrl(coords); });
      return img;
    }
  });
  function tileGet(k) { return tx('readonly', function (os) { return os.get(k); }, 'tiles').then(function (t) { return t && t.b; }); }
  var BASES = [
    {id: 'sat', name: t('Satélite'), kb: 16, url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      attribution: 'Esri, Maxar, Earthstar Geographics'},
    {id: 'topo', name: t('Topográfico'), kb: 14, url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',
      attribution: 'Esri'}
  ];  // kb: mean size of a tile (measured in Sierra Nevada, zooms 11–17), for the estimate before downloading
  BASES.forEach(function (b) { b.layer = new CachedTiles(b.url, {id: b.id, maxZoom: 19, attribution: b.attribution}); });
  var base = 0;
  var map = L.map('map', {zoomControl: false}).setView(S.view ? S.view.c : [37.09, -3.40], S.view ? S.view.z : 10);
  BASES[0].layer.addTo(map);
  L.control.zoom({position: 'topleft'}).addTo(map);
  L.control.scale({imperial: false}).addTo(map);
  map.on('moveend', function () { S.view = {c: [map.getCenter().lat, map.getCenter().lng], z: map.getZoom()}; saveSettings(); });

  var markers = L.layerGroup().addTo(map);
  var gpsLayer = L.layerGroup().addTo(map);
  var eeLayer = null;

  function drawMarkers() {
    markers.clearLayers();
    points.forEach(function (p) {
      L.circleMarker([p.lat, p.lon], {radius: 8, color: '#fff', weight: 2, fillColor: p.id === selected ? '#e8a33d' : '#2f7d4f', fillOpacity: 1})
        .bindTooltip(esc(p.name), {permanent: false})
        .on('click', function () { select(p.id); showTab('analysis'); })
        .addTo(markers);
    });
  }

  function newPointPopup(lat, lon, extra) {
    var name = t('Punto {0}', points.length + 1);
    var html = '<div class="popup-form"><b>' + lat.toFixed(5) + ', ' + lon.toFixed(5) + '</b>' + (extra || '') +
      '<input id="pp-name" value="' + esc(name) + '"><button id="pp-save" class="primary small">' + t('Guardar') + '</button>' +
      '<button id="pp-an" class="small">' + t('Analizar') + '</button></div>';
    var pop = L.popup().setLatLng([lat, lon]).setContent(html).openOn(map);
    setTimeout(function () {
      function add(go) {
        var p = addPoint($('pp-name').value || name, lat, lon);
        map.closePopup(pop);
        var back = pickReturn;
        pickReturn = null;
        if (back) { select(p.id); showTab(go ? 'analysis' : back); }
        else if (go) { select(p.id); showTab('analysis'); }
      }
      $('pp-save').onclick = function () { add(false); };
      $('pp-an').onclick = function () { add(true); };
    }, 0);
  }
  map.on('click', function (ev) { newPointPopup(ev.latlng.lat, ev.latlng.lng); });

  // A new point chosen on the map from another tab (the assistant): once saved, it is selected and that tab comes back.
  var pickReturn = null;
  function pickOnMap(tab) {
    pickReturn = tab;
    showTab('map');
    toast(t('Toca el mapa donde quieras el punto nuevo'), 5000);
  }

  function locate() {
    toast(t('Buscando la ubicación…'), 30000);
    var p = window.Android ? native('locate') : new Promise(function (resolve, reject) {
      navigator.geolocation.getCurrentPosition(function (pos) {
        resolve({lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy});
      }, function (e) { reject(new Error(e.message)); }, {enableHighAccuracy: true, timeout: 30000});
    });
    return p.then(function (loc) {
      if (loc.cancelled) throw new Error(t('cancelado'));
      $('toast').classList.add('hidden');
      gpsLayer.clearLayers();
      L.circle([loc.lat, loc.lon], {radius: loc.accuracy || 0, color: '#3a7bd5', weight: 1, fillOpacity: 0.12}).addTo(gpsLayer);
      L.circleMarker([loc.lat, loc.lon], {radius: 7, color: '#fff', weight: 2, fillColor: '#3a7bd5', fillOpacity: 1}).addTo(gpsLayer);
      return loc;
    }, function (e) { toast(t('Ubicación: {0}', errText(e)), 5000); throw e; });
  }
  function locInfo(loc) {
    return '<div class="small muted">± ' + Math.round(loc.accuracy || 0) + ' m' + (loc.stale ? ' · ' + t('posición antigua') : '') + '</div>';
  }

  $('btn-gps').onclick = function () {
    locate().then(function (loc) {
      showTab('map');
      map.setView([loc.lat, loc.lon], Math.max(map.getZoom(), 15));
      newPointPopup(loc.lat, loc.lon, locInfo(loc));
    }, function () {});
  };
  $('btn-base').onclick = function () {
    map.removeLayer(BASES[base].layer);
    base = (base + 1) % BASES.length;
    BASES[base].layer.addTo(map).bringToBack();
    toast(BASES[base].name);
  };
  $('btn-clear-layer').onclick = function () {
    if (eeLayer) { map.removeLayer(eeLayer); URL.revokeObjectURL(eeLayer._url); }
    eeLayer = null;
    $('btn-clear-layer').classList.add('hidden');
    $('layer-legend').classList.add('hidden');
  };

  // Base maps offline ------------------------------------------------------------------------------------------------
  // As in Google Maps: frame the area on the map, choose the detail and the maps, see the size, download. The tiles of
  // an area follow from its bounds and zooms, so deleting an area deletes the tiles no other area needs.

  var DL_ZMIN = 6, DL_MAX_TILES = 40000;
  function lon2x(lon, z) { return Math.floor((lon + 180) / 360 * Math.pow(2, z)); }
  function lat2y(lat, z) {
    var r = lat * Math.PI / 180;
    return Math.floor((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * Math.pow(2, z));
  }
  function tileKeys(a) {  // a: {bounds: [s, w, n, e], zmax, bases}
    var keys = [], b = a.bounds;
    a.bases.forEach(function (base) {
      for (var z = DL_ZMIN; z <= a.zmax; z++) {
        var x0 = lon2x(b[1], z), x1 = lon2x(b[3], z), y0 = lat2y(b[2], z), y1 = lat2y(b[0], z);
        for (var x = x0; x <= x1; x++) for (var y = y0; y <= y1; y++) keys.push(base + '/' + z + '/' + x + '/' + y);
      }
    });
    return keys;
  }
  function tileCount(a) {
    var n = 0, b = a.bounds;
    for (var z = DL_ZMIN; z <= a.zmax; z++) {
      n += (lon2x(b[3], z) - lon2x(b[1], z) + 1) * (lat2y(b[0], z) - lat2y(b[2], z) + 1);
    }
    return n * a.bases.length;
  }
  function mb(bytes) { return bytes >= 1073741824 ? dec((bytes / 1073741824).toFixed(2)) + ' GB' :
    dec((bytes / 1048576).toFixed(bytes < 10485760 ? 1 : 0)) + ' MB'; }
  function km(m) { return m >= 1000 ? dec((m / 1000).toFixed(m < 10000 ? 1 : 0)) + ' km' : Math.round(m) + ' m'; }
  function allAreas() { return tx('readonly', function (os) { return os.getAll(); }, 'areas'); }

  var dl = null;  // the selection in course: {running, cancel}
  function frameBounds() {
    var f = $('dl-frame').getBoundingClientRect(), m = $('map').getBoundingClientRect();
    var sw = map.containerPointToLatLng([f.left - m.left, f.bottom - m.top]);
    var ne = map.containerPointToLatLng([f.right - m.left, f.top - m.top]);
    return [sw.lat, sw.lng, ne.lat, ne.lng];
  }
  function dlArea() {
    return {bounds: frameBounds(), zmax: Number($('dl-zoom').value),
      bases: BASES.filter(function (b) { return $('dl-' + b.id).checked; }).map(function (b) { return b.id; })};
  }
  function dlEstimate() {
    if (!dl || dl.running) return;
    var a = dlArea(), b = a.bounds;
    var h = map.distance([b[0], b[1]], [b[2], b[1]]), w = map.distance([b[0], b[1]], [b[0], b[3]]);
    var n = tileCount(a), bytes = 0;
    a.bases.forEach(function (id) {
      var base = BASES.filter(function (x) { return x.id === id; })[0];
      bytes += n / a.bases.length * base.kb * 1024;
    });
    var free = dl.free !== undefined ? ' · ' + t('libre en el teléfono para la app: {0}', mb(dl.free)) : '';
    var too = n > DL_MAX_TILES;
    $('dl-est').innerHTML = t('Zona de {0} × {1}', km(w), km(h)) + '<br><b>' + (a.bases.length ? '≈ ' + mb(bytes) : t('elige un mapa')) +
      '</b> · ' + t('{0} teselas', i18n.int(n)) + '<span class="muted small">' + free + '</span>' +
      (too ? '<div class="warn">' + t('Zona demasiado grande para este detalle (máx. {0} teselas): acerca el mapa o baja el detalle.',
        i18n.int(DL_MAX_TILES)) + '</div>' : '');
    $('dl-go').disabled = too || !a.bases.length || (dl.free !== undefined && bytes > dl.free);
  }
  function dlZoomOptions() {
    var lat = map.getCenter().lat, sel = $('dl-zoom').value || S.dlZoom || '16';
    $('dl-zoom').innerHTML = [13, 14, 15, 16, 17, 18].map(function (z) {
      var res = 156543.03 * Math.cos(lat * Math.PI / 180) / Math.pow(2, z);
      var what = {13: t('vista general'), 14: t('caminos'), 15: t('senderos'), 16: t('detalle'), 17: t('mucho detalle'), 18: t('máximo')}[z];
      return '<option value="' + z + '">' + t('{0} ({1} m/píxel)', what, res < 1 ? dec(res.toFixed(1)) : Math.round(res)) + '</option>';
    }).join('');
    $('dl-zoom').value = sel;
  }
  function dlOpen() {
    if (dl) return;
    showTab('map');
    dl = {running: false};
    document.body.classList.add('dl-mode');
    $('dl-frame').classList.remove('hidden');
    $('dl-sheet').classList.remove('hidden');
    $('dl-prog').classList.add('hidden');
    $('dl-go').classList.remove('hidden');
    $('dl-go').textContent = t('Descargar');
    $('dl-cancel').textContent = t('Cancelar');
    BASES.forEach(function (b) { $('dl-' + b.id).checked = (S.dlBases || [BASES[base].id]).indexOf(b.id) >= 0; });
    allAreas().then(function (as) { $('dl-name').value = t('Zona {0}', as.length + 1); });
    dlZoomOptions();
    setTimeout(function () {
      $('dl-frame').style.bottom = ($('dl-sheet').offsetHeight + 16) + 'px';
      map.invalidateSize();
      dlEstimate();
    }, 0);
    if (navigator.storage && navigator.storage.estimate) {
      navigator.storage.estimate().then(function (est) { if (dl) { dl.free = est.quota - est.usage; dlEstimate(); } });
    }
  }
  function dlClose() {
    dl = null;
    document.body.classList.remove('dl-mode');
    $('dl-frame').classList.add('hidden');
    $('dl-sheet').classList.add('hidden');
  }
  map.on('moveend zoomend', function () { if (dl && !dl.running) { dlZoomOptions(); dlEstimate(); } });
  ['dl-zoom', 'dl-sat', 'dl-topo'].forEach(function (id) { $(id).addEventListener('change', dlEstimate); });
  $('btn-dl').onclick = dlOpen;
  $('dl-cancel').onclick = function () {
    if (dl && dl.running) { dl.cancel = true; return; }
    dlClose();
  };

  $('dl-go').onclick = function () {
    if (!navigator.onLine) return toast(t('Sin conexión: descarga la zona con wifi antes de salir'));
    var a = dlArea();
    a.id = 'a' + Date.now().toString(36);
    a.name = ($('dl-name').value || t('Zona')).slice(0, 60);
    a.created = new Date().toISOString();
    a.zmin = DL_ZMIN;
    S.dlZoom = String(a.zmax); S.dlBases = a.bases; saveSettings();
    var keys = tileKeys(a), byId = {};
    BASES.forEach(function (b) { byId[b.id] = b; });
    dl.running = true;
    $('dl-go').classList.add('hidden');
    $('dl-cancel').textContent = t('Detener');
    $('dl-prog').classList.remove('hidden');
    var done = 0, bytes = 0, failed = 0, next = 0, pending = [];
    function progress() {
      $('dl-bar').style.width = (100 * done / keys.length).toFixed(1) + '%';
      $('dl-ptext').textContent = t('{0} de {1} teselas', i18n.int(done), i18n.int(keys.length)) + ' · ' +
        mb(bytes) + (failed ? ' · ' + t('{0} fallidas', failed) : '') + '. ' + t('Deja la app abierta.');
    }
    function flush() {
      if (!pending.length) return Promise.resolve();
      var batch = pending;
      pending = [];
      return tx('readwrite', function (os) { batch.forEach(function (t) { os.put(t); }); }, 'tiles');
    }
    function fetchTile(k, tries) {
      var p = k.split('/'), b = byId[p[0]];
      var url = b.url.replace('{z}', p[1]).replace('{x}', p[2]).replace('{y}', p[3]);
      return fetch(url).then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.blob();
      }).catch(function (e) {
        if (tries > 0) return new Promise(function (res) { setTimeout(res, 800); }).then(function () { return fetchTile(k, tries - 1); });
        throw e;
      });
    }
    function worker() {
      if (dl.cancel || next >= keys.length) return Promise.resolve();
      var k = keys[next++];
      return tileGet(k).then(function (have) {
        if (have) { bytes += have.size; return; }
        return fetchTile(k, 2).then(function (blob) {
          bytes += blob.size;
          pending.push({k: k, b: blob});
          if (pending.length >= 25) return flush();
        }, function () { failed++; });
      }).then(function () { done++; if (done % 10 === 0 || done === keys.length) progress(); return worker(); });
    }
    progress();
    var workers = [];
    for (var i = 0; i < 6; i++) workers.push(worker());
    Promise.all(workers).then(flush).then(function () {
      var cancelled = dl.cancel;
      a.tiles = done; a.bytes = bytes; a.failed = failed; a.complete = !cancelled && !failed;
      return tx('readwrite', function (os) { os.put(a); }, 'areas').then(function () {
        dl.running = false;
        $('dl-cancel').textContent = t('Cerrar');
        $('dl-ptext').textContent = (cancelled ? t('Detenida: {0}, {1} teselas, {2}', a.name, i18n.int(done), mb(bytes)) :
          t('Listo: {0}, {1} teselas, {2}', a.name, i18n.int(done), mb(bytes))) +
          (failed ? ' ' + t('({0} no se pudieron descargar: vuelve a descargar la zona para completarla)', failed) : '') +
          '. ' + t('Se ve sin conexión hasta el detalle elegido.');
        BASES[base].layer.redraw();
      });
    }).catch(function (e) {
      dl.running = false;
      $('dl-cancel').textContent = t('Cerrar');
      $('dl-ptext').textContent = t('Error: {0}', errText(e)) + (/quota/i.test(errText(e)) ? ' ' + t('(sin espacio en el teléfono)') : '');
    });
  };

  function drawAreas() {
    return allAreas().then(function (as) {
      as.sort(function (a, b) { return a.created < b.created ? 1 : -1; });
      $('area-list').innerHTML = as.length ? as.map(function (a) {
        var names = a.bases.map(function (id) { return BASES.filter(function (b) { return b.id === id; })[0].name; }).join(' ' + t('y') + ' ');
        return '<li><div><div class="name">' + esc(a.name) + '</div><div class="sub">' + esc(names) + ' · ' + mb(a.bytes) + ' · ' +
          t('{0} teselas', i18n.int(a.tiles)) + ' · ' + t('hasta zoom {0}', a.zmax) + ' · ' + i18n.date(a.created) +
          (a.complete ? '' : ' · ' + t('incompleta')) + '</div></div><div class="acts"><button class="small" data-see="' + esc(a.id) +
          '">' + t('Ver') + '</button><button class="small" data-del="' + esc(a.id) + '">' + t('Borrar') + '</button></div></li>';
      }).join('') : '<li class="muted small">' + t('Aún no hay mapas descargados.') + '</li>';
      return as;
    });
  }
  var areaBox = null;
  $('area-list').onclick = function (ev) {
    var b = ev.target.closest('button');
    if (!b) return;
    allAreas().then(function (as) {
      var id = b.getAttribute('data-see') || b.getAttribute('data-del');
      var a = as.filter(function (x) { return x.id === id; })[0];
      if (!a) return;
      var bb = [[a.bounds[0], a.bounds[1]], [a.bounds[2], a.bounds[3]]];
      if (b.hasAttribute('data-see')) {
        if (a.bases.indexOf(BASES[base].id) < 0) $('btn-base').onclick();
        showTab('map');
        if (areaBox) map.removeLayer(areaBox);
        areaBox = L.rectangle(bb, {color: '#e8a33d', weight: 2, fill: false, dashArray: '6 4', interactive: false}).addTo(map);
        setTimeout(function () { if (areaBox) { map.removeLayer(areaBox); areaBox = null; } }, 8000);
        setTimeout(function () { map.invalidateSize(); map.fitBounds(bb); }, 0);
        return;
      }
      if (!confirm(t('¿Borrar el mapa sin conexión "{0}" ({1})?', a.name, mb(a.bytes)))) return;
      var keep = {};
      as.forEach(function (o) { if (o.id !== a.id) tileKeys(o).forEach(function (k) { keep[k] = 1; }); });
      var gone = tileKeys(a).filter(function (k) { return !keep[k]; });
      tx('readwrite', function (os) { gone.forEach(function (k) { os.delete(k); }); }, 'tiles').then(function () {
        return tx('readwrite', function (os) { os.delete(a.id); }, 'areas');
      }).then(function () { toast(t('Mapa borrado')); drawAreas(); drawSettings(); });
    });
  };
  $('btn-new-area').onclick = dlOpen;

  // Points -----------------------------------------------------------------------------------------------------------

  var selected = null;

  function addPoint(name, lat, lon) {
    var p = {id: newId(), name: String(name).slice(0, 80), lat: Number(lat), lon: Number(lon), created: new Date().toISOString()};
    points.push(p);
    savePoints();
    drawPoints();
    toast(t('Guardado: {0}', p.name));
    return p;
  }

  function drawPoints() {
    drawMarkers();
    var ul = $('point-list');
    if (!points.length) {
      ul.innerHTML = '<li class="muted">' + 
        t('Sin puntos. Añádelos con tu ubicación, tocando el mapa, con coordenadas o importando un GeoJSON o CSV.') + '</li>';
      return;
    }
    ul.innerHTML = points.map(function (p) {
      return '<li data-id="' + p.id + '"><div><div class="name">' + esc(p.name) + '</div><div class="sub">' +
        p.lat.toFixed(5) + ', ' + p.lon.toFixed(5) + '</div></div><div class="acts">' +
        '<button class="small" data-act="an">' + t('Analizar') + '</button><button class="small" data-act="ren">✎</button>' +
        '<button class="small" data-act="del">🗑</button></div></li>';
    }).join('');
  }
  $('point-list').onclick = function (ev) {
    var btn = ev.target.closest('button'), li = ev.target.closest('li[data-id]');
    if (!li) return;
    var p = pointById(li.getAttribute('data-id'));
    var act = btn ? btn.getAttribute('data-act') : 'an';
    if (act === 'an') { select(p.id); showTab('analysis'); }
    else if (act === 'ren') {
      var n = prompt(t('Nombre del punto'), p.name);
      if (n) { p.name = n.slice(0, 80); savePoints(); drawPoints(); if (selected === p.id) select(p.id); }
    } else if (act === 'del' && confirm(t('¿Borrar "{0}" y sus resultados guardados?', p.name))) {
      points = points.filter(function (q) { return q.id !== p.id; });
      savePoints();
      deleteResultsOf(p.id);
      if (selected === p.id) select(null);
      drawPoints();
    }
  };

  $('pt-gps').onclick = function () {
    locate().then(function (loc) {
      var n = prompt(t('Nombre del punto (± {0} m)', Math.round(loc.accuracy || 0)), t('Punto {0}', points.length + 1));
      if (n !== null) addPoint(n || t('Punto'), loc.lat, loc.lon);
    }, function () {});
  };
  $('pt-coords').onclick = function () { $('coord-form').classList.remove('hidden'); };
  $('cf-cancel').onclick = function () { $('coord-form').classList.add('hidden'); };
  $('cf-save').onclick = function () {
    var lat = parseFloat(String($('cf-lat').value).replace(',', '.')), lon = parseFloat(String($('cf-lon').value).replace(',', '.'));
    if (!(lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180)) return toast(t('Coordenadas no válidas (grados decimales WGS84)'));
    addPoint($('cf-name').value || t('Punto {0}', points.length + 1), lat, lon);
    $('coord-form').classList.add('hidden');
    $('cf-name').value = $('cf-lat').value = $('cf-lon').value = '';
  };

  // GeoJSON (Point features, properties.name) or CSV (columns name, lat, lon; also latitude/longitude, y/x)
  function parsePoints(name, text) {
    var out = [];
    if (/\.(geo)?json$/i.test(name) || /^\s*\{/.test(text)) {
      var g = JSON.parse(text);
      var feats = g.type === 'FeatureCollection' ? g.features : g.type === 'Feature' ? [g] : [];
      feats.forEach(function (f, i) {
        var geom = f.geometry || {}, pr = f.properties || {};
        var coords = geom.type === 'Point' ? [geom.coordinates] : geom.type === 'MultiPoint' ? geom.coordinates : [];
        coords.forEach(function (c, k) {
          out.push({name: pr.name || pr.Name || pr.nombre || pr.id || t('Punto {0}', (i + 1) + (k ? '.' + k : '')), lat: c[1], lon: c[0]});
        });
      });
      return out;
    }
    var lines = text.split(/\r?\n/).filter(function (l) { return l.trim(); });
    var sep = lines[0].indexOf(';') >= 0 ? ';' : ',';
    var head = lines[0].split(sep).map(function (h) { return h.trim().toLowerCase().replace(/"/g, ''); });
    function col(names) { for (var i = 0; i < head.length; i++) if (names.indexOf(head[i]) >= 0) return i; return -1; }
    var ilat = col(['lat', 'latitude', 'latitud', 'y']), ilon = col(['lon', 'lng', 'long', 'longitude', 'longitud', 'x']),
      iname = col(['name', 'nombre', 'id', 'punto']);
    if (ilat < 0 || ilon < 0) throw new Error(t('el CSV necesita columnas lat y lon'));
    lines.slice(1).forEach(function (l, i) {
      var c = l.split(sep).map(function (x) { return x.trim().replace(/^"|"$/g, ''); });
      out.push({name: iname >= 0 ? c[iname] : t('Punto {0}', i + 1), lat: parseFloat(c[ilat]), lon: parseFloat(c[ilon])});
    });
    return out;
  }
  $('pt-import').onclick = function () {
    native('openFile').then(function (f) {
      if (f.cancelled) return;
      var ps = parsePoints(f.name || '', f.text).filter(function (p) {
        return p.lat >= -90 && p.lat <= 90 && p.lon >= -180 && p.lon <= 180;
      });
      if (!ps.length) return toast(t('No encontré puntos en {0}', f.name));
      ps.forEach(function (p) {
        points.push({id: newId(), name: String(p.name).slice(0, 80), lat: Number(p.lat), lon: Number(p.lon), created: new Date().toISOString()});
      });
      savePoints();
      drawPoints();
      map.fitBounds(L.latLngBounds(ps.map(function (p) { return [p.lat, p.lon]; })).pad(0.2));
      toast(t('{0} puntos importados', ps.length));
    }).catch(function (e) { toast(t('Importar: {0}', errText(e)), 5000); });
  };
  function saveText(name, mime, text) {
    if (!window.Android) {
      var a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([text], {type: mime}));
      a.download = name;
      a.click();
      return Promise.resolve();
    }
    return native('saveFile', {name: name, mime: mime, text: text}).then(function (r) {
      if (r.ok) toast(t('Guardado: {0}', r.name || name));
    }).catch(function (e) { toast(t('Guardar: {0}', errText(e)), 5000); });
  }
  $('pt-export').onclick = function () {
    var fc = {type: 'FeatureCollection', features: points.map(function (p) {
      return {type: 'Feature', geometry: {type: 'Point', coordinates: [p.lon, p.lat]}, properties: {id: p.id, name: p.name, created: p.created}};
    })};
    saveText('puntos_campo.geojson', 'application/geo+json', JSON.stringify(fc, null, 1));
  };

  // Analysis ---------------------------------------------------------------------------------------------------------

  var themes = mo.themes();
  var usable = mo.variables().filter(function (e) { return !e.two_periods; });
  function themeVars(key) {
    var t = themes.filter(function (x) { return x.key === key; })[0];
    return usable.filter(function (e) { return t && t.indices.indexOf(e.index) >= 0; });
  }
  function varLabel(e) {
    var twins = usable.filter(function (x) { return x.index === e.index && x.sensor === e.sensor; });
    var extra = twins.length > 1 ? ' ' + String(e.col).split('/').pop() : '';
    return e.index + ' · ' + e.sensor + extra + ' (' + e.m + ' m)';
  }
  $('an-theme').innerHTML = themes.filter(function (t) { return themeVars(t.key).length; }).map(function (t) {
    return '<option value="' + t.key + '">' + esc(i18n.lang === 'en' ? (t.en || t.es) : (t.es || t.en)) + '</option>';
  }).join('');
  function fillVars() {
    var vs = themeVars($('an-theme').value);
    $('an-var').innerHTML = vs.map(function (e) { return '<option value="' + e.ref + '">' + esc(varLabel(e)) + '</option>'; }).join('');
    if (S.lastRef && vs.some(function (e) { return e.ref === S.lastRef; })) $('an-var').value = S.lastRef;
    varInfo();
  }
  function entry() { return mo.byRef(Number($('an-var').value)); }
  function varInfo() {
    var e = entry();
    S.lastRef = e.ref;
    S.lastTheme = $('an-theme').value;
    saveSettings();
    var st = Boolean(e.static);
    ['an-start', 'an-end', 'an-step', 'an-season', 'an-metric'].forEach(function (id) { $(id).disabled = st; });
    $('an-series').disabled = $('an-trend').disabled = st;
    var u = unitText(e, 'mean');
    $('an-varinfo').textContent = (i18n.lang === 'en' ? (e.vname_en || e.vname) : (e.vname || e.vname_en)) + (u ? ' · ' + u : '') +
      ' · ' + e.dr + (e.metric ? ' · ' + t('solo métrica {0}', e.metric) : '') + ' · ' + t('Datos: {0}', mo.dataSource(e));
    if (e.metric) $('an-metric').value = e.metric;
    $('an-test').disabled = st;
    var noTopo = mo.noTopographic(e);  // why the topographic correction cannot be applied, or null
    $('an-topo').disabled = Boolean(noTopo);
    $('an-topo').parentNode.title = noTopo || '';
    $('an-snowndsi').disabled = st || !mo.SNOW_NDSI[e.sensor];
    $('an-help').classList.toggle('hidden', !mo.wikiSection(e.index, i18n.lang));
  }
  // The pixel filters of the analysis: the defaults of MonitorEO, with the options checked that apply to E
  function qualityOf(e) {
    var q = {};
    if ($('an-topo').checked && !mo.noTopographic(e)) q.topographic = true;
    if ($('an-snowndsi').checked && !e.static && mo.SNOW_NDSI[e.sensor]) q.snow_ndsi = mo.SNOW_NDSI_DEFAULT;
    return q;
  }
  $('an-help').onclick = function () {
    var w = mo.wikiSection(entry().index, i18n.lang);
    if (!w) return;
    if (window.Android) native('openUrl', w.url); else window.open(w.url, '_blank');
  };
  ['an-topo', 'an-snowndsi'].forEach(function (id) {
    $(id).checked = Boolean(S[id]);
    $(id).addEventListener('change', function () { S[id] = $(id).checked; saveSettings(); });
  });
  $('an-theme').onchange = fillVars;
  $('an-var').onchange = varInfo;
  if (S.lastTheme) $('an-theme').value = S.lastTheme;
  fillVars();
  $('an-start').value = S.start || daysAgo(3 * 365);
  $('an-end').value = S.end || daysAgo(0);
  ['an-start', 'an-end', 'an-radius', 'an-step', 'an-metric', 'an-season', 'an-test'].forEach(function (id) {
    if (S[id]) $(id).value = S[id];
    $(id).addEventListener('change', function () { S[id] = $(id).value; saveSettings(); });
  });

  function season() {
    var t = $('an-season').value.trim();
    if (!t) return null;
    var m = /^(\d{2}-\d{2})\s*[\/–-]\s*(\d{2}-\d{2})$/.exec(t);
    if (!m) throw new Error(i18n.t('temporada como MM-DD/MM-DD, p. ej. 06-01/09-30'));
    return [m[1], m[2]];
  }
  // An analysis {e, spec, params, source} from plain options {ref, period, metric, radius, step, season, quality, test}:
  // those of the form (chosen) or those of the assistant (ai.js), computed by the same functions below
  function analysis(o) {
    var e = mo.byRef(Number(o.ref));
    if (!e || e.two_periods) throw new Error(t('variable desconocida: {0}', o.ref));
    var params = {ref: e.ref, radius: Number(o.radius) || 0};
    var opts = {ref: e.ref};
    if (!e.static) {
      params.period = o.period;
      if (!params.period || !params.period[0] || !params.period[1]) throw new Error(t('elige las fechas'));
      params.metric = e.metric || o.metric || 'mean';
      params.step = o.step || 'monthly';
      params.season = o.season || null;
      opts.period = params.period;
      opts.metric = params.metric;
      if (params.season) opts.season = params.season;
      var q = {};
      if (o.quality && o.quality.topographic && !mo.noTopographic(e)) q.topographic = true;
      if (o.quality && o.quality.snow_ndsi && mo.SNOW_NDSI[e.sensor]) q.snow_ndsi = mo.SNOW_NDSI_DEFAULT;
      if (Object.keys(q).length) params.quality = opts.quality = q;
      if (o.test) params.test = mo.checkTest(o.test);
    }
    return {e: e, spec: mo.spec(opts), params: params,
      source: mo.dataSource(e, params.period ? [params.period] : null)};
  }
  function chosen() {
    var e = entry();
    return analysis({ref: e.ref, radius: Number($('an-radius').value), period: [$('an-start').value, $('an-end').value],
      metric: $('an-metric').value, step: $('an-step').value, season: e.static ? null : season(), quality: qualityOf(e),
      test: $('an-test').value});
  }

  function select(id) {
    selected = id;
    drawMarkers();
    document.dispatchEvent(new Event('campo:select'));
    var p = pointById(id);
    $('an-empty').classList.toggle('hidden', Boolean(p));
    $('an-body').classList.toggle('hidden', !p);
    if (!p) return;
    $('an-name').textContent = p.name;
    $('an-coords').textContent = p.lat.toFixed(5) + ', ' + p.lon.toFixed(5) + ' · ' + mo.utmOf(p.lon, p.lat);
    status(null);
    drawResults();
  }
  $('an-goto').onclick = function () {
    var p = pointById(selected);
    showTab('map');
    map.setView([p.lat, p.lon], Math.max(map.getZoom(), 15));
  };

  var busy = false, runStart = 0, statusText = '', ticker = null;
  function elapsed() {
    var t = Math.round((Date.now() - runStart) / 1000);
    return t < 60 ? t + ' s' : Math.floor(t / 60) + ' min ' + ('0' + t % 60).slice(-2) + ' s';
  }
  function showStatus() {
    $('an-status').textContent = statusText + (busy && statusText ? ' · ' + elapsed() : '');
  }
  function status(text, error) {  // while a computation runs, with the time it has taken (it shows it is still alive)
    var s = $('an-status');
    s.classList.toggle('hidden', !text);
    s.classList.toggle('error', Boolean(error));
    statusText = text || '';
    showStatus();
    clearInterval(ticker);
    if (busy && text && !error) ticker = setInterval(showStatus, 1000);
  }
  function run(label, f) {
    if (busy) return toast(t('Espera a que termine el cálculo en curso'));
    var p = pointById(selected);
    busy = true;
    runStart = Date.now();
    status(t('{0}… (conectando con Earth Engine)', label));
    var started = runStart;
    Promise.resolve().then(function () { return connect(); }).then(function (project) {
      status(t('{0}… (Earth Engine, proyecto {1})', label, project));
      return f(p, project);
    }).then(function (r) {
      busy = false;
      status(null);
      if (!r) return;
      return keep(r, p, started).then(drawResults);
    }).catch(function (e) {
      busy = false;
      status(label + ': ' + errText(e), true);
    });
  }

  // A result of P, kept on the phone with when and how it was computed
  function keep(r, p, started) {
    r.point = p.id;
    r.computed = new Date().toISOString();
    r.seconds = Math.round((Date.now() - started) / 1000);
    r.mode = S.mode;
    return saveResult(r).then(function () { return r; });
  }

  function resultId(kind, pointId, params) {
    return [pointId, kind, params.ref, (params.period || []).join('/'), params.radius, params.metric || '',
      params.step || '', (params.season || []).join('/'), JSON.stringify(params.quality || {}), params.test || ''].join('|');
  }

  // The value of the period: the composite of the images (or the fixed layer) over the region, mean and spread
  function computeValue(p, c, project) {
    var e = c.e, r = radiusFor(c.e, c.params.radius);
    var fc = regionOf([p], r), geom = fc.geometry(), scale = scaleOf(e, r), crs = mo.utmOf(p.lon, p.lat);
    var img = mo.image(c.spec, geom, scale);
    var red = ee.Reducer.mean().combine(ee.Reducer.stdDev(), '', true).combine(ee.Reducer.minMax(), '', true)
      .combine(ee.Reducer.count(), '', true);
    var d = {stats: img.reduceRegion({reducer: red, geometry: geom, scale: scale, crs: crs, maxPixels: 1e9, tileScale: 4})};
    if (!e.static) d.images = mo.collection(c.spec, geom, scale).size();
    var params = Object.assign({}, c.params);
    delete params.step; delete params.test;
    return evaluate(ee.Dictionary(d)).then(function (v) {
      return {id: resultId('value', p.id, params), kind: 'value', params: params, scale: scale, crs: crs,
        project: project, source: c.source, stats: v.stats, images: v.images};
    });
  }
  $('an-value').onclick = function () {
    run(t('Valor del periodo'), function (p, project) { return computeValue(p, chosen(), project); });
  };

  // The time series: mo.series, as the Earth Engine app (ui.js fetchSeries)
  function seriesSteps(c) {
    mo.checkDates(c.spec);
    var steps = mo.seriesBins(c.spec, c.params.step);
    if (steps.length > MAX_STEPS) throw new Error(t('{0} pasos: como mucho {1}; acorta el periodo o usa un paso mayor', steps.length, MAX_STEPS));
    return steps;
  }
  function computeSeries(p, c, project, progress) {
    var e = c.e, r = radiusFor(c.e, c.params.radius), steps = seriesSteps(c);
    var scale = scaleOf(e, r), crs = mo.utmOf(p.lon, p.lat);
    var params = Object.assign({}, c.params);
    delete params.test;
    return new Promise(function (resolve, reject) {
      mo.series(c.spec, regionOf([p], r), 1, c.params.metric, 'mean', scale, crs, steps, function (error, rows) {
        if (error) return reject(new Error(error));
        resolve({id: resultId('series', p.id, params), kind: 'series', params: params, scale: scale, crs: crs,
          project: project, source: c.source, rows: rows.map(function (x) { return {date: x.date, value: x.value, n_pixels: x.n_pixels, n_images: x.n_images}; })});
      }, progress);
    });
  }
  $('an-series').onclick = function () {
    run(t('Serie temporal'), function (p, project) {
      return computeSeries(p, chosen(), project, function (k, n) { status(t('Serie temporal… {0} de {1} pasos', k, n)); });
    });
  };

  // The trend of the annual values: seasonalBins → series → withParts → trendRows (ui.js trendTable)
  function trendYears(c) {
    mo.checkDates(c.spec);
    var wins = mo.windows(c.spec.period, c.spec.season);
    if (wins.length < 3) throw new Error(t('la tendencia necesita al menos 3 años (mejor 8 o más)'));
    return wins;
  }
  function computeTrend(p, c, project, progress) {
    var e = c.e, r = radiusFor(c.e, c.params.radius);
    var first = trendYears(c)[0][0];
    var sbins = mo.seasonalBins(c.spec, 'annual');
    var scale = scaleOf(e, r), crs = mo.utmOf(p.lon, p.lat);
    var params = Object.assign({}, c.params, {step: 'annual', test: mo.checkTest(c.params.test || 'mk')});
    return new Promise(function (resolve, reject) {
      mo.series(c.spec, regionOf([p], r), 1, c.params.metric, 'mean', scale, crs,
        sbins.map(function (b) { return [b[2], b[3]]; }), function (error, rows) {
          if (error) return reject(new Error(error));
          try {
            var yearly = mo.withParts(rows, sbins);
            var t = mo.trendRows(yearly, 'annual', first, i18n.lang, undefined, undefined, params.test)[0];
            resolve({id: resultId('trend', p.id, params), kind: 'trend', params: params, scale: scale, crs: crs,
              project: project, source: c.source, first: first, trend: t,
              years: yearly.map(function (x) { return {year: x.year, value: x.value, n_images: x.n_images}; })});
          } catch (err) { reject(err); }
        }, progress);
    });
  }
  $('an-trend').onclick = function () {
    run(t('Tendencia'), function (p, project) {
      return computeTrend(p, chosen(), project, function (k, n) { status(t('Tendencia… {0} de {1} años', k, n)); });
    });
  };

  // The layer of the variable around the point (3 km), coloured between its percentiles 1 and 99 (mo.visParams). It is
  // kept as an image (PNG in Web Mercator over a lat/lon box, so that it lies on the map as the tiles do) with the
  // results of the point, to see it without coverage.
  // The image is computed at once for the whole circle, so at the pixels of the variable (more is not more detail,
  // only more computation: 900 px over 6 km would be ~7 m, 20× the work of Landsat at 30 m), at most LAYER_PX
  var LAYER_R = 3000, LAYER_PX = 900;
  function layerPx(e) { return Math.max(16, Math.min(LAYER_PX, Math.ceil(2 * (LAYER_R + 50) / Math.max(Number(e.m) || 10, 10)))); }
  function layerBox(p) {  // [south, west, north, east] around P, a little over LAYER_R
    var dlat = (LAYER_R + 50) / 111320, dlon = dlat / Math.cos(p.lat * Math.PI / 180);
    return [p.lat - dlat, p.lon - dlon, p.lat + dlat, p.lon + dlon];
  }
  function showLayer(r) {
    var e = mo.byRef(r.params.ref), b = r.bounds, vis = r.vis;
    if (eeLayer) { map.removeLayer(eeLayer); URL.revokeObjectURL(eeLayer._url); }
    var op = S.layerOpacity === undefined ? 85 : S.layerOpacity;
    eeLayer = L.imageOverlay(URL.createObjectURL(r.image), [[b[0], b[1]], [b[2], b[3]]], {opacity: op / 100}).addTo(map);
    $('btn-clear-layer').classList.remove('hidden');
    var u = unitText(e, r.params.metric || 'mean');
    $('layer-legend').innerHTML = '<div class="row between"><b>' + esc(varLabel(e)) + '</b>' +
      '<button id="lg-eye" class="small" title="' + esc(t('Ocultar o mostrar la capa')) + '">' + t('Ocultar') + '</button></div>' +
      (r.params.period ? r.params.period.join(' → ') : '') +
      '<div class="bar" style="background:linear-gradient(90deg,' + vis.palette.map(function (x) { return '#' + x; }).join(',') +
      ')"></div>' + num(vis.min) + ' – ' + num(vis.max) + (u ? ' ' + esc(u) : '') +
      '<label class="opacity">' + t('Opacidad') + ' <span id="lg-op">' + op + ' %</span><input id="lg-range" type="range" min="0" max="100" step="5" value="' + op + '"></label>';
    var shown_ = true;
    $('lg-range').oninput = function () {
      var v = Number($('lg-range').value);
      $('lg-op').textContent = v + ' %';
      S.layerOpacity = v;
      if (shown_) eeLayer.setOpacity(v / 100);
    };
    $('lg-range').onchange = saveSettings;
    $('lg-eye').onclick = function () {
      shown_ = !shown_;
      eeLayer.setOpacity(shown_ ? Number($('lg-range').value) / 100 : 0);
      $('lg-eye').textContent = shown_ ? t('Ocultar') : t('Mostrar');
      $('lg-range').disabled = !shown_;
    };
    $('layer-legend').classList.remove('hidden');
    showTab('map');
    setTimeout(function () { map.invalidateSize(); map.fitBounds([[b[0], b[1]], [b[2], b[3]]]); }, 0);  // once the map is shown
  }
  function computeLayer(p, c, project, progress) {
    var e = c.e;
    var area = ee.Geometry.Point([p.lon, p.lat]).buffer(LAYER_R);
    var img = mo.image(c.spec, area, undefined).clip(area);
    var scale = Math.max(Number(e.m), 30), box = layerBox(p);
    return evaluate(mo.percentiles(img, area, scale)).then(function (stats) {
      var vis = mo.visParams(stats, mo.rampEntry(e, c.params.metric || 'mean', 'period'));
      if (progress) progress(t('calculando la imagen de {0} × {1} píxeles en Earth Engine', layerPx(e), layerPx(e)));
      return new Promise(function (resolve, reject) {
        img.visualize(vis).getThumbURL({region: ee.Geometry.Rectangle([box[1], box[0], box[3], box[2]], null, false),
          dimensions: layerPx(e), format: 'png', crs: 'EPSG:3857'}, function (url, error) {
          if (error) reject(new Error(error)); else resolve(url);
        });
      }).then(function (url) { return fetch(url); }).then(function (res) {
        if (!res.ok) throw new Error(t('imagen de la capa: HTTP {0}', res.status));
        return res.blob();
      }).then(function (blob) {
        var params = Object.assign({}, c.params, {radius: LAYER_R});
        delete params.step; delete params.test;
        return {id: resultId('layer', p.id, params), kind: 'layer', params: params, scale: Number(e.m), project: project,
          source: c.source, bounds: box, vis: {min: vis.min, max: vis.max, palette: vis.palette}, image: blob};
      });
    });
  }
  $('an-layer').onclick = function () {
    run(t('Capa en el mapa'), function (p, project) {
      return computeLayer(p, chosen(), project, function (t) { status(i18n.t('Capa en el mapa… ({0})', t)); })
        .then(function (r) { showLayer(r); return r; });
    });
  };

  // The quick card of PTS: one request per variable for all of them, each at its own pixels
  function fichaPeriod(f) {
    if (f.period === 'lastYear') {
      var y = new Date().getUTCFullYear() - 1;
      return [y + '-01-01', y + '-12-31'];
    }
    return f.days ? [daysAgo(f.days), daysAgo(0)] : null;
  }
  function computeFicha(pts, radius, progress) {
    var crs = mo.utmOf(pts[0].lon, pts[0].lat);
    var out = {};  // pointId -> [{ref, period, metric, value, n, error}]
    pts.forEach(function (p) { out[p.id] = []; });
    var done = 0;
    return Promise.all(FICHA.map(function (f) {
      var e = mo.byRef(f.ref), period = fichaPeriod(f), rad = radiusFor(e, radius), scale = scaleOf(e, rad);
      function put(values, error) {
        pts.forEach(function (p) {
          var v = values ? values[p.id] : null;
          out[p.id].push({ref: f.ref, period: period, metric: f.metric || null, scale: scale,
            value: v ? v.mean : null, n: v ? v.count : 0, error: error || null});
        });
        done++;
        if (progress) progress(done, FICHA.length);
      }
      try {
        var opts = {ref: f.ref};
        if (period) { opts.period = period; opts.metric = f.metric; }
        var s = mo.spec(opts), fc = regionOf(pts, rad);
        var img = mo.image(s, fc.geometry(), scale);
        var red = ee.Reducer.mean().combine(ee.Reducer.count(), '', true);
        var rows = img.reduceRegions({collection: fc, reducer: red, scale: scale, crs: crs, tileScale: 4})
          .map(function (ft) { return ee.Feature(null, {id: ft.get('name'), mean: ft.get('mean'), count: ft.get('count')}); });
        return evaluate(rows).then(function (fcv) {
          var values = {};
          fcv.features.forEach(function (ft) { values[ft.properties.id] = ft.properties; });
          put(values);
        }, function (err) { put(null, errText(err)); });
      } catch (err) {
        put(null, errText(err));
        return null;
      }
    })).then(function () {
      out.order = FICHA.map(function (f) { return f.ref; });
      return out;
    });
  }
  function fichaRecord(p, rows, radius, project) {
    rows.sort(function (a, b) {
      return FICHA.findIndex(function (f) { return f.ref === a.ref; }) - FICHA.findIndex(function (f) { return f.ref === b.ref; });
    });
    return {id: p.id + '|ficha|' + radius, kind: 'ficha', params: {radius: radius}, project: project, items: rows};
  }
  $('an-ficha').onclick = function () {
    run(t('Ficha rápida'), function (p, project) {
      var radius = Number($('an-radius').value);
      return computeFicha([p], radius, function (k, n) { status(t('Ficha rápida… {0} de {1} variables', k, n)); })
        .then(function (out) { return fichaRecord(p, out[p.id], radius, project); });
    });
  };

  $('pt-precompute').onclick = function () {
    if (!points.length) return toast(t('No hay puntos'));
    if (busy) return toast(t('Espera a que termine el cálculo en curso'));
    var radius = Number($('an-radius').value);
    var info = S.mode === 'shared' ? usage().catch(function () { return ''; }) : Promise.resolve('');
    info.then(function (u) {
      if (!confirm(t('{0} puntos × {1} variables (radio {2} m).', points.length, FICHA.length, radius) + '\n' +
        (u ? u + '\n' : '') + t('¿Calcular y guardar en el teléfono?'))) return;
      busy = true;
      $('pre-status').textContent = t('Conectando con Earth Engine…');
      var groups = {};  // by UTM zone, so that each one computes in its own CRS
      points.forEach(function (p) { var z = mo.utmOf(p.lon, p.lat); (groups[z] = groups[z] || []).push(p); });
      return connect().then(function (project) {
        var zones = Object.keys(groups), saved = 0;
        return zones.reduce(function (prev, z, i) {
          return prev.then(function () {
            return computeFicha(groups[z], radius, function (k, n) {
              $('pre-status').textContent = t('Zona {0} de {1}: {2} de {3} variables', i + 1, zones.length, k, n);
            }).then(function (out) {
              return Promise.all(groups[z].map(function (p) {
                var r = fichaRecord(p, out[p.id], radius, project);
                r.point = p.id; r.computed = new Date().toISOString(); r.mode = S.mode;
                saved++;
                return saveResult(r);
              }));
            });
          });
        }, Promise.resolve()).then(function () {
          busy = false;
          $('pre-status').textContent = t('Listo: ficha de {0} puntos guardada ({1}).', saved, i18n.dateTime(new Date()));
          if (selected) drawResults();
        });
      });
    }).catch(function (e) {
      busy = false;
      $('pre-status').textContent = t('Error: {0}', errText(e));
    });
  };

  // Results ----------------------------------------------------------------------------------------------------------

  var charts = [];
  var TEST_NAMES = {'mk': 'Mann-Kendall', 'hamed-rao': 'Hamed-Rao', 'tfpw': 'TFPW'};
  var KIND = {ficha: t('Ficha rápida'), value: t('Valor del periodo'), series: t('Serie temporal'), trend: t('Tendencia'), layer: t('Capa')};

  function meta(r) {
    var p = r.params || {}, bits = [];
    if (p.period) bits.push(p.period.join(' → '));
    if (p.season) bits.push(t('temporada {0}', p.season.join('/')));
    if (p.metric) bits.push(t('métrica {0}', p.metric));
    if (p.step && r.kind === 'series') bits.push(t('paso {0}', p.step));
    if (p.quality && p.quality.topographic) bits.push(t('corrección topográfica SCS+C'));
    if (p.quality && p.quality.snow_ndsi) bits.push(t('nieve por NDSI ≥ {0}', dec(p.quality.snow_ndsi)));
    if (p.test) bits.push(t('test {0}', TEST_NAMES[p.test]));
    bits.push(r.kind === 'layer' ? t('círculo de {0} km', dec(p.radius / 1000)) : p.radius ? t('radio {0} m', p.radius) : t('píxel del punto'));
    if (r.scale) bits.push(t('píxeles de {0} m', r.scale));
    bits.push(t('calculado {0}', i18n.dateTime(r.computed)) + (r.seconds ? ' (' + r.seconds + ' s)' : ''));
    bits.push(r.mode === 'sa' ? t('proyecto {0}', r.project) : t('cuenta compartida de MonitorEO'));
    if (r.source) bits.push(t('Datos: {0}', r.source));
    return bits.join(' · ');
  }

  function csvOf(r) {
    var e = r.params && r.params.ref ? mo.byRef(r.params.ref) : null;
    var p = pointById(r.point) || {};
    var head = 'point,lat,lon,';
    var lines = [];
    if (r.kind === 'series') {
      lines.push(head + 'variable,sensor,date,value,n_pixels,n_images');
      r.rows.forEach(function (x) { lines.push([p.name, p.lat, p.lon, e.index, e.sensor, x.date, x.value, x.n_pixels, x.n_images].join(',')); });
    } else if (r.kind === 'trend') {
      lines.push(head + 'variable,sensor,year,value,n_images');
      r.years.forEach(function (x) { lines.push([p.name, p.lat, p.lon, e.index, e.sensor, x.year, x.value, x.n_images].join(',')); });
    } else if (r.kind === 'ficha') {
      lines.push(head + 'variable,sensor,start,end,metric,value,unit,n_pixels');
      r.items.forEach(function (x) {
        var en = mo.byRef(x.ref);
        lines.push([p.name, p.lat, p.lon, en.index, en.sensor, x.period ? x.period[0] : '', x.period ? x.period[1] : '',
          x.metric || '', x.value, unitText(en, x.metric || 'mean'), x.n].join(','));
      });
    } else {
      var s = r.stats || {};
      lines.push(head + 'variable,sensor,start,end,metric,mean,std,min,max,n_pixels,n_images');
      lines.push([p.name, p.lat, p.lon, e.index, e.sensor, r.params.period ? r.params.period[0] : '', r.params.period ? r.params.period[1] : '',
        r.params.metric || '', s.value_mean, s.value_stdDev, s.value_min, s.value_max, s.value_count, r.images].join(','));
    }
    return lines.join('\n') + '\n';
  }

  function cardHtml(r, i) {
    var e = r.params && r.params.ref ? mo.byRef(r.params.ref) : null;
    var title = KIND[r.kind] + (e ? ' · ' + varLabel(e) : '');
    var body = '';
    if (r.kind === 'ficha') {
      body = '<table>' + r.items.map(function (x) {
        var en = mo.byRef(x.ref), u = unitText(en, x.metric || 'mean');
        var per = x.period ? (x.period[0].slice(0, 4) === x.period[1].slice(0, 4) && /01-01$/.test(x.period[0]) && /12-31$/.test(x.period[1]) ?
          x.period[0].slice(0, 4) : x.period[0].slice(5) + '→' + x.period[1].slice(5)) : i18n.t('fija');
        return '<tr><td>' + esc(en.index) + ' <span class="muted small">' + esc(en.sensor) + '</span></td><td class="num">' +
          (x.error ? '<span class="muted small" title="' + esc(x.error) + '">' + i18n.t('error') + '</span>' :
            x.value === null ? '<span class="muted small">' + i18n.t('sin imágenes') + '</span>' : num(x.value) + ' ' + esc(u)) +
          '</td><td class="muted small">' + esc(per) + '</td></tr>';
      }).join('') + '</table>';
    } else if (r.kind === 'value') {
      var s = r.stats || {}, u = unitText(e, r.params.metric || 'mean');
      body = s.value_mean === null || s.value_mean === undefined ? '<div class="muted">' + i18n.t('Sin datos en el periodo (nubes, nieve o sin imágenes).') + '</div>' :
        '<div class="big">' + num(s.value_mean) + ' <span class="small muted">' + esc(u) + '</span></div><table>' +
        '<tr><td>' + i18n.t('Desviación típica') + '</td><td class="num">' + num(s.value_stdDev) + '</td></tr>' +
        '<tr><td>' + i18n.t('Mínimo – máximo') + '</td><td class="num">' + num(s.value_min) + ' – ' + num(s.value_max) + '</td></tr>' +
        '<tr><td>' + i18n.t('Píxeles') + '</td><td class="num">' + num(s.value_count, 0) + '</td></tr>' +
        (r.images !== undefined ? '<tr><td>' + i18n.t('Imágenes') + '</td><td class="num">' + num(r.images, 0) + '</td></tr>' : '') + '</table>';
    } else if (r.kind === 'series') {
      var vals = r.rows.filter(function (x) { return x.value !== null; });
      body = vals.length ? '<div class="chart-box"><canvas data-chart="' + i + '"></canvas></div>' +
        '<div class="small muted">' + i18n.t('{0} de {1} pasos con datos', vals.length, r.rows.length) + '</div>' :
        '<div class="muted">' + i18n.t('Sin datos en el periodo.') + '</div>';
    } else if (r.kind === 'trend') {
      var t = r.trend || {}, ut = unitText(e, r.params.metric || 'mean');
      body = '<div class="chart-box"><canvas data-chart="' + i + '"></canvas></div><table>' +
        '<tr><td>' + i18n.t('Años con datos (n)') + '</td><td class="num">' + num(t.n, 0) + ' (' + (t.first_year || '—') + '–' + (t.last_year || '—') + ')</td></tr>' +
        '<tr><td>' + i18n.t('Pendiente de Sen') + '</td><td class="num"><b>' + num(t.slope) + '</b> ' + esc((ut || '') + i18n.t('/año')) + '</td></tr>' +
        '<tr><td>' + i18n.t('τ de Kendall') + '</td><td class="num">' + num(t.tau, 3) + '</td></tr>' +
        '<tr><td>p (' + esc(TEST_NAMES[r.params.test || 'mk']) + ')</td><td class="num">' + num(t.p_value, 3) + '</td></tr>' +
        '<tr><td>' + esc(i18n.t('Significativa (p < {0})', dec('0.05'))) + '</td><td class="num">' + (t.significant ? i18n.t('sí') : i18n.t('no')) + '</td></tr></table>';
    } else if (r.kind === 'layer') {
      var ul = unitText(e, r.params.metric || 'mean');
      body = '<img class="layer-img" data-img="' + i + '" alt="">' +
        '<div class="bar" style="background:linear-gradient(90deg,' + r.vis.palette.map(function (x) { return '#' + x; }).join(',') + ')"></div>' +
        '<div class="small muted">' + num(r.vis.min) + ' – ' + num(r.vis.max) + (ul ? ' ' + esc(ul) : '') + '</div>';
    }
    var first = r.kind === 'layer' ? '<button class="small primary" data-show="' + i + '">' + i18n.t('Ver en el mapa') + '</button>' :
      '<button class="small" data-csv="' + i + '">CSV</button>';
    return '<div class="card result"><h4>' + esc(title) + '</h4><div class="meta">' + esc(meta(r)) + '</div>' + body +
      '<div class="acts">' + first + '<button class="small" data-del="' + i + '">' + i18n.t('Borrar') + '</button></div></div>';
  }

  var shown = [], imgUrls = [];
  function drawResults() {
    charts.forEach(function (c) { c.destroy(); });
    charts = [];
    imgUrls.forEach(function (u) { URL.revokeObjectURL(u); });
    imgUrls = [];
    if (!selected) return;
    var pointId = selected;
    return resultsOf(pointId).then(function (rs) {
      if (pointId !== selected) return;
      rs.sort(function (a, b) { return a.computed < b.computed ? 1 : -1; });
      shown = rs;
      $('an-results').innerHTML = rs.length ? '<div class="muted small" style="margin:0 2px 8px">' + t('Resultados guardados en el teléfono ({0})', rs.length) + '</div>' +
        rs.map(cardHtml).join('') : '<div class="muted small">' + t('Aún no hay resultados guardados para este punto.') + '</div>';
      rs.forEach(function (r, i) {
        var im = document.querySelector('img[data-img="' + i + '"]');
        if (im && r.image) { var u = URL.createObjectURL(r.image); imgUrls.push(u); im.src = u; }
        var cv = document.querySelector('canvas[data-chart="' + i + '"]');
        if (cv) charts.push(chartFor(cv, r));
      });
    });
  }
  // The chart of a series or a trend R in the canvas CV
  function chartFor(cv, r) {
    var ink = getComputedStyle(document.documentElement).getPropertyValue('--muted').trim() || '#666';
    var ds, labels;
    if (r.kind === 'series') {
      labels = r.rows.map(function (x) { return x.date; });
      ds = [{data: r.rows.map(function (x) { return x.value; }), borderColor: '#2f7d4f', backgroundColor: '#2f7d4f',
        pointRadius: 2, borderWidth: 1.5, spanGaps: true}];
    } else {
      labels = r.years.map(function (x) { return x.year; });
      var t = r.trend || {};
      ds = [{data: r.years.map(function (x) { return x.value; }), borderColor: '#2f7d4f', backgroundColor: '#2f7d4f',
        pointRadius: 3, borderWidth: 1.5, spanGaps: true, label: i18n.t('valor anual')}];
      if (t.slope !== null && t.slope !== undefined) {
        ds.push({data: r.years.map(function (x) { return t.intercept + t.slope * (x.year - r.first); }),
          borderColor: '#e8a33d', borderDash: [6, 4], pointRadius: 0, borderWidth: 2, label: 'Sen'});
      }
    }
    return new Chart(cv, {type: 'line', data: {labels: labels, datasets: ds},
      options: {responsive: true, maintainAspectRatio: false, animation: false,
        plugins: {legend: {display: false}},
        scales: {x: {ticks: {color: ink, maxTicksLimit: 6}}, y: {ticks: {color: ink}}}}});
  }
  $('an-results').onclick = function (ev) {
    var b = ev.target.closest('button');
    if (!b) return;
    var r = shown[Number(b.getAttribute('data-csv') || b.getAttribute('data-del') || b.getAttribute('data-show'))];
    if (!r) return;
    if (b.hasAttribute('data-show')) {
      showLayer(r);
    } else if (b.hasAttribute('data-csv')) {
      var p = pointById(r.point) || {name: 'punto'};
      var e = r.params && r.params.ref ? mo.byRef(r.params.ref) : null;
      var name = [p.name, r.kind, e ? e.index + '_' + e.sensor : ''].filter(Boolean).join('_').replace(/[^\w.-]+/g, '_') + '.csv';
      saveText(name, 'text/csv', csvOf(r));
    } else if (confirm(t('¿Borrar este resultado?'))) {
      deleteResult(r.id).then(drawResults);
    }
  };

  // Settings -------------------------------------------------------------------------------------------------------

  function usage() {
    return httpJson(broker() + '/usage?user=' + S.userId).then(function (r) {
      if (r.status !== 200) throw new Error(r.data.error || ('broker ' + r.status));
      var d = r.data;
      if (d.restricted) return t('Earth Engine ha puesto la cuenta compartida en modo restringido (ha gastado su cuota del mes): los cálculos serán lentos o fallarán. Usa tu cuenta de servicio hasta el {0}.', d.resets);
      return t('Te quedan {0} de {1} horas EECU este mes (se renuevan el {2}).', num(d.left_hours, 1), num(d.limit_hours, 0), d.resets);
    });
  }
  function drawSettings() {
    document.querySelectorAll('input[name=mode]').forEach(function (r) { r.checked = r.value === S.mode; });
    $('shared-box').classList.toggle('hidden', S.mode !== 'shared');
    $('sa-box').classList.toggle('hidden', S.mode !== 'sa');
    $('user-id').textContent = S.userId;
    $('sa-project').value = S.project || '';
    if (S.mode === 'sa') {
      native('serviceAccountInfo').then(function (i) {
        $('sa-info').textContent = i.client_email ? t('Cuenta: {0} · proyecto del JSON: {1}', i.client_email, i.project_id) :
          t('Sin cuenta de servicio: elige su archivo JSON (cópialo antes al teléfono).');
        $('sa-project').placeholder = i.project_id || t('(el del JSON)');
      }).catch(function (e) { $('sa-info').textContent = errText(e); });
    }
    drawAreas();
    if (navigator.storage && navigator.storage.estimate) {
      navigator.storage.estimate().then(function (est) {
        $('storage-info').textContent = t('{0} puntos · {1} MB usados por la app', points.length, dec((est.usage / 1048576).toFixed(1)));
      });
    }
  }
  document.querySelectorAll('input[name=mode]').forEach(function (r) {
    r.onchange = function () { S.mode = r.value; saveSettings(); connecting = null; drawSettings(); };
  });
  $('sa-project').onchange = function () { S.project = $('sa-project').value.trim(); saveSettings(); connecting = null; };
  $('btn-sa').onclick = function () {
    native('pickServiceAccount').then(function (i) {
      if (i.cancelled) return;
      toast(t('Cuenta de servicio guardada: {0}', i.client_email));
      connecting = null;
      drawSettings();
    }).catch(function (e) { toast(errText(e), 6000); });
  };
  $('btn-sa-clear').onclick = function () {
    if (!confirm(t('¿Olvidar la cuenta de servicio guardada en el teléfono?'))) return;
    native('clearServiceAccount').then(function () { connecting = null; drawSettings(); });
  };
  $('btn-usage').onclick = function () {
    $('usage').textContent = t('Consultando…');
    usage().then(function (t) { $('usage').textContent = t; }, function (e) { $('usage').textContent = errText(e); });
  };
  $('btn-test').onclick = function () {
    $('conn-status').textContent = t('Conectando…');
    connecting = null;
    connect().then(function (project) {
      return evaluate(ee.Number(1).add(1)).then(function () {
        $('conn-status').textContent = t('Conectado a Earth Engine con el proyecto {0}.', project);
      });
    }).catch(function (e) { $('conn-status').textContent = t('Error: {0}', errText(e)); });
  };
  $('btn-clear-results').onclick = function () {
    if (!confirm(t('¿Borrar todos los resultados guardados? Los puntos se conservan.'))) return;
    tx('readwrite', function (os) { os.clear(); }).then(function () { drawResults(); toast(t('Resultados borrados')); drawSettings(); });
  };
  var about = (mo.CATALOG.about || {});
  $('about').innerHTML = '<div class="app-version">MonitorEO Campo <b id="app-version">—</b>' +
    (about.version ? ' · ' + t('núcleo de MonitorEO {0}', esc(about.version)) : '') + '</div><b>MonitorEO</b> (' +
    t('Observatorio de Cambio Global de Sierra Nevada, Universidad de Granada') + '). ' +
    t('Calcula en Google Earth Engine con el mismo código que la app de Earth Engine de MonitorEO') +
    (about.version ? ' (' + t('versión {0}', esc(about.version)) + ')' : '') + '.<br>' + t('Cita:') + ' Observatorio de Cambio Global de Sierra ' +
    'Nevada (2026). MonitorEO [Software]. Zenodo. https://doi.org/10.5281/zenodo.23814894 · Gorelick et al. (2017). ' +
    'Google Earth Engine. Remote Sensing of Environment, 202, 18–27. https://doi.org/10.1016/j.rse.2017.06.031. ' +
    t('Contiene datos modificados de Copernicus Sentinel; Landsat por cortesía del USGS.');

  // Suggest a change or report an error, as in the other tools of MonitorEO (monitoreo.about.feedback('campo', version)):
  // an issue of GitHub or the anonymous form, both filled with the tool and the version
  var FEEDBACK_TOOL = ['Field app', 'Field app / App de campo'];  // monitoreo.about.TOOLS['campo']
  function feedbackLinks(version) {
    var q = function (o) { return Object.keys(o).map(function (k) { return k + '=' + encodeURIComponent(o[k]); }).join('&'); };
    var issue = {tool: FEEDBACK_TOOL[0]}, form = {usp: 'pp_url', 'entry.1706228456': FEEDBACK_TOOL[1]};
    if (version) issue.version = form['entry.1533130685'] = version;
    return {issue: 'https://github.com/monitoreo-obsnev/monitoreo/issues/new/choose?' + q(issue),
            form: 'https://docs.google.com/forms/d/e/1FAIpQLSddJakYhTHL2sVhIQtUX5rC7gYuaAAWYQ4krgFxS3-nzZMg0w/viewform?' + q(form)};
  }
  function drawFeedback(version) {
    var f = feedbackLinks(version), box = document.createElement('div');
    box.className = 'feedback';
    box.innerHTML = '<br><b>' + t('Sugerir un cambio o informar de un error') + '</b>: ' +
      t('{0}en GitHub{1} (público, con una cuenta de GitHub) o {2}formulario anónimo{1} (sin cuenta, nombre ni correo).',
        '<a href="#" data-url="' + esc(f.issue) + '">', '</a>', '<a href="#" data-url="' + esc(f.form) + '">');
    box.querySelectorAll('a').forEach(function (a) {
      a.onclick = function (e) {
        e.preventDefault();
        var url = a.getAttribute('data-url');
        if (window.Android) native('openUrl', url); else window.open(url, '_blank');
      };
    });
    var old = $('about').querySelector('.feedback');
    if (old) old.parentNode.removeChild(old);
    $('about').appendChild(box);
  }
  drawFeedback('');

  native('appInfo').then(function (i) {  // the version of the APK installed (versionName of app/build.gradle)
    $('app-version').textContent = i.version;
    $('brand-version').textContent = 'v' + i.version;
    drawFeedback(i.version);
  }).catch(function () { $('app-version').textContent = t('(navegador)'); });

  // Tabs, network, back button ---------------------------------------------------------------------------------------

  var current = 'map';
  function showTab(name) {
    current = name;
    document.querySelectorAll('.tab').forEach(function (t) { t.classList.toggle('active', t.id === 'tab-' + name); });
    document.querySelectorAll('nav button').forEach(function (b) { b.classList.toggle('active', b.getAttribute('data-tab') === name); });
    if (name === 'map') setTimeout(function () { map.invalidateSize(); }, 0);
    if (name === 'settings') drawSettings();
  }
  document.querySelectorAll('nav button').forEach(function (b) { b.onclick = function () { showTab(b.getAttribute('data-tab')); }; });
  window.onBack = function () {
    if (dl) { if (!dl.running) dlClose(); return true; }
    if (map._popup && map.hasLayer(map._popup)) { map.closePopup(); return true; }
    if (current !== 'map') { showTab('map'); return true; }
    return false;
  };
  function net() {
    $('net').textContent = navigator.onLine ? t('con conexión') : t('sin conexión');
    $('net').classList.toggle('off', !navigator.onLine);
  }
  window.addEventListener('online', net);
  window.addEventListener('offline', net);
  net();

  drawPoints();
  if (points.length && !S.view) map.fitBounds(L.latLngBounds(points.map(function (p) { return [p.lat, p.lon]; })).pad(0.2));

  // What the assistant (ai.js) uses: the same computations, results and map as the buttons
  window.campo = {pickOnMap: pickOnMap, 
    mo: mo, S: S, saveSettings: saveSettings, native: native, toast: toast, esc: esc, num: num, unitText: unitText,
    errText: errText, map: map, points: function () { return points; }, pointById: pointById, addPoint: addPoint,
    selected: function () { return selected; }, select: select, showTab: showTab, locate: locate,
    usable: usable, themes: themes, varLabel: varLabel, analysis: analysis, connect: connect, usage: usage,
    seriesSteps: seriesSteps, trendYears: trendYears, computeValue: computeValue, computeSeries: computeSeries,
    computeTrend: computeTrend, computeLayer: computeLayer, computeFicha: computeFicha, fichaRecord: fichaRecord,
    keep: keep, resultsOf: resultsOf, drawResults: drawResults, cardHtml: cardHtml, chartFor: chartFor,
    showLayer: showLayer, regionOf: regionOf, saveResult: saveResult, FICHA: FICHA, KIND: KIND, meta: meta,
    daysAgo: daysAgo, broker: broker
  };
})();
