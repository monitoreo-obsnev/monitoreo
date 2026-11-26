/*
 * MonitorEO Campo: the assistant (tab Preguntar). A language model chooses the variable and the computation that answer
 * a question about the points of the trip, the app runs them with its own functions (window.campo: lib/core.js in
 * Earth Engine, the same as the buttons of Análisis), keeps each result with the point, and the model explains it.
 *
 * The model is, by default, that of MonitorEO: the route /chat of its broker, as the assistant of the monitoreo package
 * (monitoreo/assistant.py, chat_cloud), with the anonymous ID of this installation; the broker chooses it (Claude, or
 * Gemini while Claude has no credit) and keeps its keys. In Ajustes the user may choose instead their own key of
 * Claude, Gemini or GLM (Z.ai); the key stays in the private storage of Android (MainActivity.aiRequest adds it), never
 * in this page. Like the broker, the conversation is kept in the form of the OpenAI chat completions API, with the
 * blocks of each model (the thinking of Claude, the thought signatures of Gemini) in extra_content, sent back as they
 * came; the requests to Claude and Gemini with their own keys are translated here as the broker does (claude_params,
 * claude_answer, gemini_request) and those of GLM as the assistant of monitoreo does (glm_messages, chat_glm: with the
 * backup key of GLM of the broker when the user's key fails).
 *
 * Unlike the assistant of monitoreo, whose model only gets a receipt of each result, here the model gets the values
 * (aggregated numbers: a mean, a series, a trend) to answer questions in the field; see INTEGRACION.md.
 */
(function () {
  'use strict';

  var C = window.campo, mo = C.mo, S = C.S, esc = C.esc;
  function $(id) { return document.getElementById(id); }

  var PROVIDERS = {
    monitoreo: {name: t('Modelo de MonitorEO'), short: 'MonitorEO', key: false},
    claude: {name: 'Claude (Anthropic)', short: 'Claude', key: true, model: 'claude-opus-5-5',
      help: 'console.anthropic.com → API keys'},
    gemini: {name: 'Gemini (Google)', short: 'Gemini', key: true, model: 'gemini-3.8-flash',
      help: 'aistudio.google.com → Get API key'},
    glm: {name: 'GLM (Z.ai)', short: 'GLM', key: true, model: 'glm-4.7-flash',
      help: t('z.ai → API keys (glm-4.7-flash y glm-4.5-flash son gratis)')}
  };
  var GLM_FREE = ['glm-4.7-flash', 'glm-4.5-flash'];  // those of the backup key of GLM of the broker (GLM_MODELS)
  var CLAUDE_FALLBACKS = ['claude-opus-5-5', 'claude-sonnet-5-5'];  // with fallbacks "default" (as the broker)
  var REASONING = 'low';  // the effort of reasoning (CHAT_REASONING of the broker)
  var MAX_TOKENS = 8192;
  var MAX_STEPS = 8;  // answers of the model to one message of the user (MAX_STEPS of monitoreo)
  var MAX_BYTES = 2 * 1048576 - 65536;  // of a request to the broker (CLOUD_MAX_BYTES of monitoreo)
  var GEMINI_DROP = ['title', 'default', 'additionalProperties', '$schema'];
  var NOTE = '\n\n(Nota de la aplicación, no del usuario: ';

  if (!S.aiProvider || !PROVIDERS[S.aiProvider]) S.aiProvider = 'monitoreo';
  S.aiModels = S.aiModels || {};
  function modelOf(p) { return (S.aiModels[p] || PROVIDERS[p].model || '').trim(); }
  function vname(e) { return i18n.lang === 'en' ? e.vname_en || e.vname : e.vname || e.vname_en; }
  function rawErr(e) { return (e && e.message) || String(e); }  // the message as it came (Spanish), for the model and tests

  // The instructions --------------------------------------------------------------------------------------------------

  function firstYear(dr) { var y = String(dr || '').match(/(?:19|20)\d\d/g); return y ? y.sort()[0] : '?'; }
  function variablesText() {
    return C.usable.map(function (e) {
      var twins = C.usable.filter(function (x) { return x.index === e.index && x.sensor === e.sensor; });
      return e.ref + ' ' + e.index + ' ' + e.sensor + (twins.length > 1 ? ' ' + String(e.col).split('/').pop() : '') +
        ' ' + e.m + ' m ' + (e.static ? 'capa fija' : 'desde ' + firstYear(e.dr)) + (e.metric ? ' solo ' + e.metric : '') +
        ' · ' + vname(e);
    }).join('\n');
  }
  function instructions() {
    return 'Eres el asistente de MonitorEO Campo, la app de campo de MonitorEO-OBSNEV (Observatorio de Cambio Global ' +
      'de Sierra Nevada, Universidad de Granada), para gestores de espacios naturales y técnicos que están en el ' +
      'campo con el teléfono. Hoy es ' + new Date().toISOString().slice(0, 10) + '.\n\n' +
      'Qué haces: respondes preguntas sobre los puntos del viaje (vegetación, agua, nieve, temperatura, clima, ' +
      'relieve) calculando las variables de MonitorEO en Google Earth Engine con las herramientas, y explicas el ' +
      'resultado.\n\n' +
      'Reglas:\n' +
      '1. Todo número sale de una herramienta: nunca inventes valores, referencias de variables ni puntos.\n' +
      '2. Antes de calcular, mira resultados_guardados del punto: si uno ya responde (misma variable y periodo ' +
      'parecido), úsalo y di de cuándo es.\n' +
      '3. Si falta algo esencial (el punto, la variable o las fechas), propón una opción razonable y pregunta en una ' +
      'sola frase, sin llamar herramientas.\n' +
      '4. «Aquí», «donde estoy»: llama a ubicacion; para calcular en ese sitio guarda antes el punto (guardar_punto).\n' +
      '5. Elección del sensor: Sentinel-2 (10–20 m, desde 2017) para la vegetación, el agua y la nieve de un punto; ' +
      'Landsat (30 m, desde 1984) para series largas y la temperatura de superficie (LST); MODIS (250–1000 m, ' +
      'diario) para zonas amplias; ERA5-Land, TerraClimate o CHIRPS para el clima; Copernicus para elevación y ' +
      'pendiente. Tendencias: al menos 8 años; con temporada (p. ej. 06-01/09-30 en verano) si la variable cambia ' +
      'con las estaciones.\n' +
      '6. Al explicar: da el valor con su unidad, el periodo y el tamaño de píxel. Una tendencia solo es ' +
      'significativa con p < 0,05; di n (años). Nubes, nieve o sombras pueden dejar periodos sin datos: dilo si pasa.\n' +
      (i18n.lang === 'en' ?
        '7. La interfaz de la app está en inglés: responde siempre en inglés (salvo que el usuario escriba en otro ' +
        'idioma: entonces en el suyo), breve (se lee en un teléfono: 2–6 frases), sin tablas largas: la app ya muestra ' +
        'el gráfico o la tabla de cada resultado. Termina con una línea «Data: …» con la fuente que dé la herramienta.\n' :
        '7. Responde en el idioma del último mensaje del usuario, breve (se lee en un teléfono: 2–6 frases), sin tablas ' +
        'largas: la app ya muestra el gráfico o la tabla de cada resultado. Termina con una línea «Datos: …» con la ' +
        'fuente que dé la herramienta.\n') +
      '8. No nombres tus herramientas internas: di lo que haces.\n' +
      '9. Si el usuario no acepta un cálculo largo, propón uno más corto (menos años, paso mayor).\n\n' +
      'Las fechas van como AAAA-MM-DD. Variables de MonitorEO (ref, índice, sensor, píxel, desde, nombre):\n' +
      variablesText();
  }
  function contextNote() {
    var p = C.pointById(C.selected()), bits = [];
    bits.push(p ? 'punto elegido: «' + p.name + '» (id ' + p.id + ', ' + p.lat.toFixed(5) + ', ' + p.lon.toFixed(5) + ')' :
      'no hay punto elegido');
    bits.push(C.points().length + ' puntos guardados');
    bits.push('radio por defecto ' + (Number(S['an-radius'] || 100) || 'píxel del punto') + ' m');
    bits.push(navigator.onLine ? 'con conexión' : 'sin conexión');
    bits.push(S.mode === 'sa' ? 'cuenta de servicio propia' : 'cuenta compartida de MonitorEO');
    return NOTE + bits.join('; ') + ')';
  }

  // The tools (in the form of OpenAI; plain JSON Schema, which Gemini also takes) -----------------------------------

  function fn(name, description, props, required) {
    return {type: 'function', function: {name: name, description: description,
      parameters: {type: 'object', properties: props || {}, required: required || []}}};
  }
  var P_PUNTO = {type: 'string', description: 'id del punto (de puntos o del contexto); por omisión, el punto elegido'};
  var P_REF = {type: 'integer', description: 'ref de la variable (lista de las instrucciones)'};
  var P_INI = {type: 'string', description: 'inicio, AAAA-MM-DD'};
  var P_FIN = {type: 'string', description: 'fin, AAAA-MM-DD'};
  var P_MET = {type: 'string', enum: ['mean', 'median', 'max', 'min'], description: 'métrica de las imágenes de cada píxel (por omisión mean)'};
  var P_RAD = {type: 'integer', description: 'radio del círculo en m (0: el píxel del punto); por omisión el de la app'};
  var P_TEMP = {type: 'string', description: 'temporada de cada año MM-DD/MM-DD, p. ej. 06-01/09-30 (opcional)'};
  var P_TOPO = {type: 'boolean', description: 'corrección topográfica SCS+C de la reflectancia de Landsat (opcional)'};
  var P_NIEVE = {type: 'boolean', description: 'quitar también como nieve los píxeles con NDSI ≥ 0,4 (opcional)'};
  var TOOLS = [
    fn('puntos', 'Los puntos guardados en el teléfono (id, nombre, coordenadas) y cuál está elegido.'),
    fn('ubicacion', 'La ubicación actual del GPS del teléfono (lat, lon, precisión).'),
    fn('guardar_punto', 'Guarda un punto nuevo (p. ej. la ubicación actual) y lo elige; devuelve su id.',
      {nombre: {type: 'string'}, lat: {type: 'number'}, lon: {type: 'number'}}, ['nombre', 'lat', 'lon']),
    fn('variable', 'Qué mide una variable, su unidad, sensor, píxel, fechas, fuente de datos y opciones.',
      {ref: P_REF}, ['ref']),
    fn('resultados_guardados', 'Los resultados ya calculados y guardados de un punto (ficha, valores, series, ' +
      'tendencias, capas), con su fecha de cálculo. Úsalo antes de calcular.', {punto: P_PUNTO}),
    fn('ficha', 'Ficha rápida del punto: NDVI, EVI, NDWI y NDSI de Sentinel-2 (60 días), LST de Landsat (90 días), ' +
      'precipitación ERA5-Land del último año, elevación y pendiente.', {punto: P_PUNTO, radio: P_RAD}),
    fn('valor', 'El valor de una variable en el punto en un periodo (compuesto de las imágenes con la métrica; ' +
      'para las capas fijas sin fechas): media, desviación, mínimo, máximo, píxeles e imágenes.',
      {punto: P_PUNTO, ref: P_REF, inicio: P_INI, fin: P_FIN, metrica: P_MET, radio: P_RAD,
        correccion_topografica: P_TOPO, nieve_ndsi: P_NIEVE}, ['ref']),
    fn('serie', 'Serie temporal de una variable en el punto.',
      {punto: P_PUNTO, ref: P_REF, inicio: P_INI, fin: P_FIN,
        paso: {type: 'string', enum: ['monthly', '16-day', 'annual'], description: 'paso (por omisión monthly)'},
        metrica: P_MET, temporada: P_TEMP, radio: P_RAD, correccion_topografica: P_TOPO, nieve_ndsi: P_NIEVE},
      ['ref', 'inicio', 'fin']),
    fn('tendencia', 'Tendencia de los valores anuales (pendiente de Sen y test), con temporada opcional.',
      {punto: P_PUNTO, ref: P_REF, inicio: P_INI, fin: P_FIN, metrica: P_MET, temporada: P_TEMP,
        test: {type: 'string', enum: ['mk', 'hamed-rao', 'tfpw'], description: 'mk (Mann-Kendall, por omisión), hamed-rao o tfpw (corrigen la autocorrelación)'},
        radio: P_RAD, correccion_topografica: P_TOPO, nieve_ndsi: P_NIEVE}, ['ref', 'inicio', 'fin']),
    fn('capa', 'Mapa de la variable en un círculo de 3 km alrededor del punto (se muestra en el mapa de la app).',
      {punto: P_PUNTO, ref: P_REF, inicio: P_INI, fin: P_FIN, metrica: P_MET, correccion_topografica: P_TOPO,
        nieve_ndsi: P_NIEVE}, ['ref'])
  ];
  var LABELS = {puntos: t('Puntos guardados'), ubicacion: t('Ubicación del GPS'), guardar_punto: t('Guardar el punto'),
    variable: t('Ficha de la variable'), resultados_guardados: t('Resultados guardados'), ficha: t('Ficha rápida'),
    valor: t('Valor del periodo'), serie: t('Serie temporal'), tendencia: t('Tendencia'), capa: t('Capa en el mapa')};

  // Running the tools -----------------------------------------------------------------------------------------------

  function round(v) {
    if (v === null || v === undefined || isNaN(v)) return null;
    v = Number(v);
    return Math.abs(v) >= 100 ? Math.round(v * 10) / 10 : Number(v.toPrecision(4));
  }
  function pointOf(a) {
    var id = a.punto || C.selected();
    var p = C.pointById(id) || C.points().filter(function (x) { return x.name.toLowerCase() === String(id || '').toLowerCase(); })[0];
    if (!p) throw new Error(id ? 'no hay ningún punto «' + id + '»: mira puntos' : 'no hay punto elegido: pregunta al usuario cuál, o usa ubicacion y guardar_punto');
    return p;
  }
  function seasonOf(t) {
    if (!t) return null;
    if (Array.isArray(t)) return t;
    var m = /^(\d{2}-\d{2})\s*[\/–-]\s*(\d{2}-\d{2})$/.exec(String(t).trim());
    if (!m) throw new Error('temporada como MM-DD/MM-DD');
    return [m[1], m[2]];
  }
  function analysisOf(a, step) {
    var e = mo.byRef(Number(a.ref));
    if (!e) throw new Error('no hay variable con ref ' + a.ref);
    var period = e.static ? null : [a.inicio || C.daysAgo(60), a.fin || C.daysAgo(0)];
    return C.analysis({ref: e.ref, period: period, metric: a.metrica || 'mean',
      radius: a.radio === undefined || a.radio === null ? Number(S['an-radius'] || 100) : Number(a.radio),
      step: step || a.paso || 'monthly', season: seasonOf(a.temporada), test: a.test,
      quality: {topographic: Boolean(a.correccion_topografica), snow_ndsi: Boolean(a.nieve_ndsi)}});
  }
  function described(r) {
    var e = r.params && r.params.ref ? mo.byRef(r.params.ref) : null, p = r.params || {};
    var o = {resultado: C.KIND[r.kind], calculado: r.computed};
    if (e) {
      o.variable = e.index + ' · ' + e.sensor + ' (' + vname(e) + ')';
      o.unidad = C.unitText(e, p.metric || 'mean') || 'sin unidad';
    }
    if (p.period) o.periodo = p.period.join(' → ');
    if (p.season) o.temporada = p.season.join('/');
    if (p.metric) o.metrica = p.metric;
    o.radio_m = r.kind === 'layer' ? 3000 : p.radius || 0;
    if (r.scale) o.pixel_m = r.scale;
    if (p.quality) o.filtros = p.quality;
    if (r.source) o.fuente = r.source;
    return o;
  }
  function summary(r, rows) {
    var o = described(r);
    if (r.kind === 'value') {
      var s = r.stats || {};
      Object.assign(o, {media: round(s.value_mean), desviacion: round(s.value_stdDev), minimo: round(s.value_min),
        maximo: round(s.value_max), pixeles: s.value_count, imagenes: r.images});
      if (s.value_mean === null || s.value_mean === undefined) o.nota = 'sin datos en el periodo (nubes, nieve o sin imágenes)';
    } else if (r.kind === 'series') {
      var vals = r.rows.filter(function (x) { return x.value !== null; });
      o.pasos = r.rows.length;
      o.pasos_con_datos = vals.length;
      var shown = r.rows.slice(-(rows || 400));
      o.valores = shown.map(function (x) { return [x.date, round(x.value)]; });
      if (shown.length < r.rows.length) o.nota = 'solo los últimos ' + shown.length + ' pasos';
    } else if (r.kind === 'trend') {
      var t = r.trend || {};
      Object.assign(o, {test: p(r.params.test), anos: r.years.map(function (x) { return [x.year, round(x.value)]; }),
        n: t.n, pendiente_sen_por_ano: round(t.slope), tau_kendall: round(t.tau), p: round(t.p_value),
        significativa_p_005: Boolean(t.significant)});
    } else if (r.kind === 'ficha') {
      o.radio_m = r.params.radius;
      o.variables = r.items.map(function (x) {
        var en = mo.byRef(x.ref);
        return {variable: en.index + ' · ' + en.sensor, periodo: x.period ? x.period.join(' → ') : 'fija', metrica: x.metric,
          valor: x.error ? null : round(x.value), unidad: C.unitText(en, x.metric || 'mean'), pixel_m: x.scale,
          pixeles: x.n, error: x.error || undefined};
      });
    } else if (r.kind === 'layer') {
      Object.assign(o, {color_min_p1: round(r.vis.min), color_max_p99: round(r.vis.max),
        nota: 'el mapa se muestra en la app; tú no lo ves'});
    }
    return o;
    function p(test) { return {mk: 'Mann-Kendall', 'hamed-rao': 'Hamed-Rao', tfpw: 'TFPW'}[test || 'mk']; }
  }

  var RUNNERS = {
    puntos: function () {
      var sel = C.selected();
      return C.points().map(function (p) {
        return {id: p.id, nombre: p.name, lat: round(p.lat), lon: round(p.lon), elegido: p.id === sel || undefined};
      });
    },
    ubicacion: function () {
      return C.locate().then(function (l) {
        return {lat: Number(l.lat.toFixed(6)), lon: Number(l.lon.toFixed(6)), precision_m: Math.round(l.accuracy || 0),
          antigua: Boolean(l.stale)};
      });
    },
    guardar_punto: function (a) {
      if (!isFinite(a.lat) || !isFinite(a.lon) || Math.abs(a.lat) > 90 || Math.abs(a.lon) > 180) throw new Error('coordenadas no válidas');
      var p = C.addPoint(a.nombre || t('Punto'), a.lat, a.lon);
      C.select(p.id);
      return {id: p.id, nombre: p.name};
    },
    variable: function (a) {
      var e = mo.byRef(Number(a.ref));
      if (!e) throw new Error('no hay variable con ref ' + a.ref);
      var w = mo.wikiSection(e.index, i18n.lang);
      return {ref: e.ref, indice: e.index, nombre: vname(e), tipo: e.type, sensor: e.sensor,
        coleccion: e.col, pixel_m: e.m, fechas: e.dr, paso_de_las_imagenes: e.tr, unidad: C.unitText(e, 'mean'),
        capa_fija: Boolean(e.static), solo_metrica: e.metric || undefined, fuente: mo.dataSource(e),
        correccion_topografica: mo.noTopographic(e) ? 'no: ' + mo.noTopographic(e) : 'sí',
        nieve_ndsi: e.static || !mo.SNOW_NDSI[e.sensor] ? 'no' : 'sí', manual: w ? w.url : undefined};
    },
    resultados_guardados: function (a) {
      var p = pointOf(a);
      return C.resultsOf(p.id).then(function (rs) {
        rs.sort(function (x, y) { return x.computed < y.computed ? 1 : -1; });
        return {punto: p.name, resultados: rs.map(function (r) { return summary(r, 60); })};
      });
    },
    ficha: function (a, ctx) {
      var p = pointOf(a), radius = a.radio === undefined || a.radio === null ? Number(S['an-radius'] || 100) : Number(a.radio);
      return compute(ctx, p, function (project) {
        return C.computeFicha([p], radius, function (k, n) { ctx.progress(t('{0} de {1} variables', k, n)); })
          .then(function (out) { return C.fichaRecord(p, out[p.id], radius, project); });
      });
    },
    valor: function (a, ctx) {
      var p = pointOf(a), c = analysisOf(a);
      return compute(ctx, p, function (project) { return C.computeValue(p, c, project); });
    },
    serie: function (a, ctx) {
      var p = pointOf(a), c = analysisOf(a), n = C.seriesSteps(c).length;
      return ask(ctx, n > 60, t('La serie tiene {0} pasos de {1} · {2} ({3}): puede tardar varios minutos.', n,
        c.e.index, c.e.sensor, c.params.period.join(' → '))).then(function () {
        return compute(ctx, p, function (project) {
          return C.computeSeries(p, c, project, function (k, m) { ctx.progress(t('{0} de {1} pasos', k, m)); });
        });
      });
    },
    tendencia: function (a, ctx) {
      var p = pointOf(a), c = analysisOf(a, 'annual'), years = C.trendYears(c).length;
      var heavy = years > 12 || (years > 8 && Number(c.e.m) <= 30 && !c.params.season);
      return ask(ctx, heavy, t('La tendencia usa {0} años de {1} · {2} ({3}): puede tardar varios minutos.', years,
        c.e.index, c.e.sensor, c.params.season ? t('temporada {0}', c.params.season.join('/')) : t('años completos')))
        .then(function () {
        return compute(ctx, p, function (project) {
          return C.computeTrend(p, c, project, function (k, m) { ctx.progress(t('{0} de {1} años', k, m)); });
        });
      });
    },
    capa: function (a, ctx) {
      var p = pointOf(a), c = analysisOf(a);
      var days = c.params.period ? (Date.parse(c.params.period[1]) - Date.parse(c.params.period[0])) / 864e5 : 0;
      return ask(ctx, days > 2 * 366 && Number(c.e.m) <= 30, t('La capa compone {0} años de {1} a {2} m en 3 km: ' +
        'puede tardar varios minutos.', Math.round(days / 365), c.e.sensor, c.e.m)).then(function () {
        return compute(ctx, p, function (project) {
          return C.computeLayer(p, c, project, function (t) { ctx.progress(t); });
        });
      });
    }
  };
  // A computation of P in Earth Engine, kept with its results, drawn in the chat and summarized for the model
  function compute(ctx, p, f) {
    var started = Date.now();
    ctx.progress(t('conectando con Earth Engine'));
    return C.connect().then(function (project) {
      ctx.progress(t('Earth Engine, proyecto {0}', project));
      return f(project);
    }).then(function (r) { return C.keep(r, p, started); }).then(function (r) {
      ctx.result(r, p);
      if (C.selected() === p.id) C.drawResults();
      return summary(r);
    });
  }
  // Asks the user before a long computation (when HEAVY); rejects if they do not want it
  function ask(ctx, heavy, text) {
    if (!heavy) return Promise.resolve();
    return ctx.confirm(text).then(function (yes) {
      if (!yes) throw new Error('el usuario no quiso este cálculo largo: propón uno más corto');
    });
  }

  // The language models -----------------------------------------------------------------------------------------------

  function wireMessages(messages) {  // the conversation as the API of OpenAI takes it: arguments as JSON text
    return messages.map(function (m) {
      if (!m.tool_calls) return m;
      return Object.assign({}, m, {content: m.content || '', tool_calls: m.tool_calls.map(function (c) {
        var f = Object.assign({}, c.function);
        f.arguments = typeof f.arguments === 'string' ? f.arguments : JSON.stringify(f.arguments || {});
        return Object.assign({}, c, {type: 'function', function: f});
      })});
    });
  }
  function openaiAnswer(answer) {  // monitoreo assistant.openai_answer: arguments as objects, the rest as it came
    var message = Object.assign({}, ((answer.choices || [{}])[0] || {}).message || {});
    var out = {};
    Object.keys(message).forEach(function (k) { if (['tool_calls', 'content', 'role', 'refusal'].indexOf(k) < 0) out[k] = message[k]; });
    out.role = 'assistant';
    out.content = String(message.content || '').replace(/<think>[\s\S]*?<\/think>/g, '').trim();
    var calls = (message.tool_calls || []).map(function (c, i) {
      var f = Object.assign({}, c.function), a = f.arguments;
      if (typeof a === 'string') { try { a = JSON.parse(a || '{}'); } catch (e) { a = {}; } }
      return Object.assign({}, c, {id: c.id || 'call_' + i, function: Object.assign(f, {arguments: a && typeof a === 'object' ? a : {}})});
    });
    if (calls.length) out.tool_calls = calls;
    out.model = answer.model;
    return out;
  }
  function errorText(r) {
    var d = r.data, e = d && (Array.isArray(d) ? d[0] : d);
    var msg = e && (typeof e.error === 'string' ? e.error : e.error && e.error.message) || (r.text || '').slice(0, 300);
    return 'HTTP ' + r.status + (msg ? ': ' + msg : '');
  }
  function post(provider, body, extra) {
    var text = JSON.stringify(body);
    if (provider === 'monitoreo' && text.length > MAX_BYTES) {
      return Promise.reject(new Error(t('la conversación es demasiado larga para el modelo de MonitorEO: empieza una nueva')));
    }
    return C.native('aiRequest', Object.assign({provider: provider, body: text}, extra || {})).then(function (r) {
      var d = null;
      try { d = JSON.parse(r.body); } catch (e) { /* not JSON */ }
      return {status: r.status, data: d, text: r.body};
    });
  }

  // monitoreo: the broker of MonitorEO (assistant.chat_cloud)
  function chatMonitoreo(messages, tools, model) {
    var body = {messages: wireMessages(messages), tools: tools, temperature: 0.2};
    if (model) body.model = model;
    return post('monitoreo', body, {url: C.broker() + '/chat?user=' + S.userId}).then(function (r) {
      if (r.status !== 200) {
        var d = r.data || {}, err = new Error(i18n.tr(d.error || errorText(r)) +
          (d.code === 'day' || d.code === 'user' ? '' : t(' (en Ajustes puedes usar tu propia clave de Claude, Gemini o GLM)')));
        err.code = d.code;
        throw err;
      }
      return openaiAnswer(r.data);
    });
  }

  // Claude with the key of the user (broker claude_params and claude_answer)
  function claudeParams(messages, tools, model) {
    var system = [], out = [];
    messages.forEach(function (m) {
      var text = typeof m.content === 'string' ? m.content : '';
      if (m.role === 'system') system.push(text);
      else if (m.role === 'assistant') {
        var blocks = ((m.extra_content || {}).anthropic || {}).content;
        if (!blocks || !blocks.length) {
          blocks = text.trim() ? [{type: 'text', text: text}] : [];
          (m.tool_calls || []).forEach(function (c, i) {
            var a = c.function.arguments;
            if (typeof a === 'string') { try { a = JSON.parse(a || '{}'); } catch (e) { a = {}; } }
            blocks.push({type: 'tool_use', id: c.id || 'call_' + i, name: c.function.name, input: a || {}});
          });
        }
        if (blocks.length) out.push({role: 'assistant', content: blocks});
      } else if (m.role === 'tool') {
        var res = {type: 'tool_result', tool_use_id: m.tool_call_id || '', content: text};
        var last = out[out.length - 1];
        if (last && last.role === 'user' && Array.isArray(last.content) &&
          last.content.every(function (b) { return b.type === 'tool_result'; })) last.content.push(res);
        else out.push({role: 'user', content: [res]});
      } else out.push({role: 'user', content: text});
    });
    var params = {model: model, max_tokens: MAX_TOKENS, messages: out,
      system: [{type: 'text', text: system.join('\n\n'), cache_control: {type: 'ephemeral'}}],
      cache_control: {type: 'ephemeral'},
      thinking: {type: 'adaptive', block_binding: {prefix_mismatch_behavior: 'drop_block'}},
      output_config: {effort: REASONING},
      tools: tools.map(function (t) {
        return {name: t.function.name, description: t.function.description, input_schema: t.function.parameters};
      })};
    var betas = ['thinking-binding-controls-2026-08-01'];
    if (CLAUDE_FALLBACKS.indexOf(model) >= 0) {
      betas.push('server-side-fallback-2026-07-01');
      params.fallbacks = 'default';
    }
    return {params: params, betas: betas};
  }
  function claudeAnswer(response) {
    var blocks = response.content || [], message;
    if (response.stop_reason === 'refusal') {
      message = {role: 'assistant', content: t('Claude ha declinado esta petición.')};
    } else {
      message = {role: 'assistant', content: blocks.filter(function (b) { return b.type === 'text'; })
        .map(function (b) { return b.text || ''; }).join('\n\n').trim()};
      var calls = blocks.filter(function (b) { return b.type === 'tool_use'; }).map(function (b) {
        return {id: b.id, type: 'function', function: {name: b.name, arguments: JSON.stringify(b.input || {})}};
      });
      if (calls.length) message.tool_calls = calls;
      if (blocks.length) message.extra_content = {anthropic: {content: blocks}};
    }
    return {model: response.model, choices: [{index: 0, message: message, finish_reason: response.stop_reason}]};
  }
  function chatClaude(messages, tools) {
    var q = claudeParams(wireMessages(messages), tools, modelOf('claude'));
    return post('claude', q.params, {beta: q.betas.join(',')}).then(function (r) {
      if (r.status !== 200) throw new Error('Claude: ' + errorText(r));
      return openaiAnswer(claudeAnswer(r.data));
    });
  }

  // Gemini with the key of the user, by its API compatible with OpenAI (broker gemini_request)
  function geminiSchema(s) {
    if (Array.isArray(s)) return s.map(geminiSchema);
    if (!s || typeof s !== 'object') return s;
    var o = {};
    Object.keys(s).forEach(function (k) { if (GEMINI_DROP.indexOf(k) < 0) o[k] = s[k]; });
    if (o.properties) {
      var props = {};
      Object.keys(o.properties).forEach(function (k) { props[k] = geminiSchema(o.properties[k]); });
      o.properties = props;
    }
    if (o.items) o.items = geminiSchema(o.items);
    return o;
  }
  function googleOnly(obj) {
    var x = Object.assign({}, obj), extra = x.extra_content;
    if (extra && extra.google) x.extra_content = {google: extra.google}; else delete x.extra_content;
    return x;
  }
  function chatGemini(messages, tools) {
    var body = {model: modelOf('gemini'), stream: false, temperature: 0.2, reasoning_effort: REASONING,
      tools: tools.map(function (t) {
        var f = Object.assign({}, t.function), params = geminiSchema(f.parameters || {});
        if (params.properties && Object.keys(params.properties).length) f.parameters = params; else delete f.parameters;
        return {type: 'function', function: f};
      }),
      messages: wireMessages(messages).map(function (m) {
        m = googleOnly(m);
        if (m.tool_calls) m.tool_calls = m.tool_calls.map(googleOnly);
        return m;
      })};
    return post('gemini', body).then(function (r) {
      if (r.status !== 200) throw new Error('Gemini: ' + errorText(r));
      return openaiAnswer(r.data);
    });
  }

  // GLM with the key of the user and, if it fails, the backup key of the broker (assistant.chat_glm)
  function glmMessages(messages) {
    return wireMessages(messages).map(function (m) {
      var keep = {role: m.role, content: m.content || ''};
      if (m.tool_call_id) keep.tool_call_id = m.tool_call_id;
      if (m.tool_calls) {
        keep.tool_calls = m.tool_calls.map(function (c) {
          return {id: c.id, type: 'function', function: {name: c.function.name, arguments: c.function.arguments || '{}'}};
        });
      }
      return keep;
    });
  }
  function chatGlm(messages, tools) {
    var chosen = modelOf('glm'), errors = [], conversation = glmMessages(messages);
    var models = [chosen].concat(GLM_FREE.filter(function (m) { return m !== chosen; }));
    function attempt(i) {
      if (i >= models.length) return backup();
      var body = {model: models[i], messages: conversation, tools: tools, temperature: 0.2, thinking: {type: 'disabled'}};
      return post('glm', body).then(function (r) {
        if (r.status === 400 && /thinking/i.test(r.text || '')) { delete body.thinking; return post('glm', body); }
        return r;
      }).then(function (r) {
        if (r.status === 200) return openaiAnswer(r.data);
        errors.push(t('{0}, tu clave: {1}', models[i], errorText(r)));
        if (r.status === 401 || r.status === 403) return backup();
        return attempt(i + 1);
      }, function (e) {
        errors.push(t('{0}, tu clave: {1}', models[i], C.errText(e)));
        if (/no hay clave/.test(rawErr(e))) return backup();
        return attempt(i + 1);
      });
    }
    function backup() {
      return chatMonitoreo(messages, tools, GLM_FREE.indexOf(chosen) >= 0 ? chosen : GLM_FREE[0]).catch(function (e) {
        errors.push(t('la clave de reserva de MonitorEO: {0}', C.errText(e)));
        throw new Error(t('GLM no responde: {0}', errors.join('; ')));
      });
    }
    return attempt(0);
  }

  var CHAT = {monitoreo: function (m, t) { return chatMonitoreo(m, t); }, claude: chatClaude, gemini: chatGemini, glm: chatGlm};

  // The conversation ------------------------------------------------------------------------------------------------

  var conv = [];      // the messages since the last «Nueva», without the system message (in the form of OpenAI)
  var running = null; // {stopped} of the answer that runs
  var charts = [], urls = [];

  function md(text) {  // the little markdown of the answers: bold, italics, lists, line breaks
    var h = esc(text).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<i>$2</i>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');
    return h.split(/\n{2,}/).map(function (para) {
      var lines = para.split('\n');
      if (lines.every(function (l) { return /^\s*([-*•]|\d+[.)])\s+/.test(l); })) {
        return '<ul>' + lines.map(function (l) { return '<li>' + l.replace(/^\s*([-*•]|\d+[.)])\s+/, '') + '</li>'; }).join('') + '</ul>';
      }
      return '<p>' + lines.join('<br>') + '</p>';
    }).join('');
  }
  function add(cls, html) {
    var d = document.createElement('div');
    d.className = cls;
    d.innerHTML = html;
    $('ask-log').appendChild(d);
    scroll();
    return d;
  }
  function scroll() { var l = $('ask-log'); setTimeout(function () { l.scrollTop = l.scrollHeight; }, 0); }
  function stepLine(box, label) {
    var s = document.createElement('div');
    s.className = 'step';
    s.innerHTML = '<span class="mark">⏳</span> <span class="lab">' + esc(label) + '</span> <span class="muted prog"></span>';
    box.appendChild(s);
    scroll();
    return s;
  }
  function argsLabel(name, a) {
    var bits = [LABELS[name] || name];
    var e = a && a.ref ? mo.byRef(Number(a.ref)) : null;
    if (e) bits.push(e.index + ' · ' + e.sensor);
    if (a && a.inicio && a.fin) bits.push(a.inicio + ' → ' + a.fin);
    if (a && a.temporada) bits.push(t('temporada {0}', a.temporada));
    var p = a && a.punto ? C.pointById(a.punto) : null;
    if (p) bits.push(p.name);
    return bits.join(' · ');
  }
  function resultCard(box, r, p) {
    var key = 'ai' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
    var d = document.createElement('div');
    d.innerHTML = C.cardHtml(r, key);
    var card = d.firstChild;
    card.classList.add('in-chat');
    var acts = card.querySelector('.acts');
    acts.innerHTML = (r.kind === 'layer' ? '<button class="small primary" data-act="map">' + esc(t('Ver en el mapa')) +
      '</button>' : '') + '<button class="small" data-act="an">' + esc(t('Ver en Análisis')) + '</button>';
    acts.onclick = function (ev) {
      var b = ev.target.closest('button');
      if (!b) return;
      if (b.getAttribute('data-act') === 'map') C.showLayer(r);
      else { C.select(p.id); C.showTab('analysis'); }
    };
    box.appendChild(card);
    var im = card.querySelector('img[data-img]');
    if (im && r.image) { var u = URL.createObjectURL(r.image); urls.push(u); im.src = u; }
    var cv = card.querySelector('canvas[data-chart]');
    if (cv) charts.push(C.chartFor(cv, r));
    scroll();
  }
  function confirmCard(box, text) {
    return new Promise(function (resolve) {
      var d = document.createElement('div');
      d.className = 'confirm';
      d.innerHTML = '⚠ ' + esc(text) + '<div class="acts"><button class="small primary" data-yes="1">' +
        esc(t('Calcular')) + '</button><button class="small" data-yes="0">' + esc(t('Cancelar')) + '</button></div>';
      d.onclick = function (ev) {
        var b = ev.target.closest('button');
        if (!b) return;
        d.querySelectorAll('button').forEach(function (x) { x.disabled = true; });
        resolve(b.getAttribute('data-yes') === '1');
      };
      box.appendChild(d);
      scroll();
    });
  }

  function send(text) {
    text = String(text || '').trim();
    if (!text || running) return;
    if (!navigator.onLine) {
      add('ai', '<p>' + t('Sin conexión no puedo preguntar al modelo. Los resultados guardados de cada punto están en ' +
        '<b>Análisis</b> y se ven sin cobertura.') + '</p>');
      return;
    }
    $('ask-input').value = '';
    autosize();
    drawContext();
    add('me', esc(text));
    conv.push({role: 'user', content: text + contextNote()});
    var run = running = {stopped: false};
    setBusy(true);
    var box = add('ai', '');
    var steps = document.createElement('div');
    steps.className = 'steps';
    box.appendChild(steps);
    var thinking = stepLine(steps, t('Pensando ({0})', providerTitle()));
    var provider = S.aiProvider, tools = TOOLS, n = 0;

    function next() {
      if (run.stopped) return Promise.resolve();
      if (++n > MAX_STEPS) throw new Error(t('demasiados pasos para una pregunta: hazla más concreta'));
      return CHAT[provider]([{role: 'system', content: instructions()}].concat(conv), tools).then(function (m) {
        if (run.stopped) return;
        done(thinking);
        if (m.model) box.setAttribute('data-model', m.model);
        var calls = m.tool_calls || [];
        var keep = Object.assign({}, m);
        delete keep.model;
        conv.push(keep);
        if (m.content) {
          var tx = document.createElement('div');  // not t: that is the translation
          tx.className = 'text';
          tx.innerHTML = md(m.content);
          box.appendChild(tx);
          scroll();
        }
        if (!calls.length) return;
        return calls.reduce(function (prev, c) {
          return prev.then(function () { return runTool(c); });
        }, Promise.resolve()).then(function () {
          if (run.stopped) return;
          thinking = stepLine(steps, t('Pensando'));
          return next();
        });
      });
    }
    function runTool(c) {
      var name = c.function.name, a = c.function.arguments || {}, line = stepLine(steps, argsLabel(name, a));
      var started = Date.now(), timer = setInterval(function () {
        line.querySelector('.prog').textContent = (line._p ? line._p + ' · ' : '') + Math.round((Date.now() - started) / 1000) + ' s';
      }, 1000);
      var ctx = {
        progress: function (t) { line._p = t; },
        result: function (r, p) { resultCard(box, r, p); },
        confirm: function (t) { return confirmCard(box, t); }
      };
      return Promise.resolve().then(function () {
        if (run.stopped) throw new Error('detenido por el usuario');
        if (!RUNNERS[name]) throw new Error('herramienta desconocida: ' + name);
        return RUNNERS[name](a, ctx);
      }).then(function (out) {
        clearInterval(timer);
        done(line);
        line.querySelector('.prog').textContent = Math.round((Date.now() - started) / 1000) + ' s';
        conv.push({role: 'tool', tool_call_id: c.id, content: JSON.stringify(out)});
        drawContext();
      }, function (e) {
        clearInterval(timer);
        done(line, true);
        line.querySelector('.prog').textContent = C.errText(e);
        conv.push({role: 'tool', tool_call_id: c.id, content: JSON.stringify({error: rawErr(e)})});
      });
    }
    next().catch(function (e) {
      done(thinking, true);
      var er = document.createElement('div');
      er.className = 'err';
      er.textContent = C.errText(e);
      box.appendChild(er);
      // the conversation keeps going: a turn of the model without answer is closed with the error
      var last = conv[conv.length - 1];
      if (last && last.role === 'user') conv.pop();
      unanswered();
    }).then(function () {
      if (running === run) { running = null; setBusy(false); }
      var model = box.getAttribute('data-model');
      if (model) {
        var src = document.createElement('div');
        src.className = 'by';
        src.textContent = providerTitle(model);
        box.appendChild(src);
      }
      scroll();
    });
  }
  function unanswered() {  // calls of the model without answer (stopped, failed) get one, as the APIs require
    var last = conv[conv.length - 1];
    if (!last || last.role !== 'assistant' || !last.tool_calls) {
      // also calls answered only in part
      var i = conv.length - 1;
      while (i >= 0 && conv[i].role === 'tool') i--;
      if (i < 0 || !conv[i].tool_calls) return;
      last = conv[i];
    }
    var answered = conv.filter(function (m) { return m.role === 'tool'; }).map(function (m) { return m.tool_call_id; });
    last.tool_calls.forEach(function (c) {
      if (answered.indexOf(c.id) < 0) conv.push({role: 'tool', tool_call_id: c.id, content: JSON.stringify({error: 'no se hizo'})});
    });
  }
  function done(line, failed) {
    if (!line) return;
    line.querySelector('.mark').textContent = failed ? '✕' : '✓';
    line.classList.toggle('failed', Boolean(failed));
  }
  function setBusy(b) {
    $('ask-send').textContent = b ? '■' : '➤';
    $('ask-send').title = b ? t('Detener') : t('Enviar');
    $('ask-send').classList.toggle('stop', b);
  }
  function stop() {
    if (!running) return;
    running.stopped = true;
    running = null;
    unanswered();
    setBusy(false);
    add('ai muted small', esc(t('Detenido.')));
  }
  function providerTitle(model) {
    var p = PROVIDERS[S.aiProvider];
    if (S.aiProvider === 'monitoreo') return model ? t('Modelo de MonitorEO ({0})', model) : t('Modelo de MonitorEO');
    return t('{0} · {1} · tu clave', p.short, model || modelOf(S.aiProvider));
  }
  function newChat() {
    if (running) stop();
    conv = [];
    charts.forEach(function (c) { c.destroy(); });
    urls.forEach(function (u) { URL.revokeObjectURL(u); });
    charts = []; urls = [];
    $('ask-log').innerHTML = '';
    welcome();
  }
  var SUGGESTIONS = [t('¿Cómo está la vegetación en este punto?'), t('¿El NDVI de verano está aumentando aquí desde 2017?'),
    t('¿Cuánto llovió el año pasado aquí?'), t('Calcula la ficha de mi ubicación actual')];
  function welcome() {
    var d = add('ai', '<p>' + esc(t('Pregúntame por los puntos de tu viaje: calculo las variables de MonitorEO en ' +
      'Earth Engine y te explico el resultado, que queda guardado con el punto.')) + '</p><div class="sugg">' +
      SUGGESTIONS.map(function (s) { return '<button class="small">' + esc(s) + '</button>'; }).join('') + '</div>');
    d.querySelector('.sugg').onclick = function (ev) {
      var b = ev.target.closest('button');
      if (b) send(b.textContent);
    };
  }
  function drawContext() {
    var p = C.pointById(C.selected());
    $('ask-ctx').innerHTML = '<button id="ask-point" class="c pick" title="' + esc(t('Elegir el punto')) + '">📍 <b>' +
      esc(p ? p.name : t('sin punto elegido')) + '</b> ▾</button>' +
      '<span class="c">' + esc(providerTitle()) + '</span>';
    $('ask-point').onclick = togglePick;
    if (!$('ask-pick').classList.contains('hidden')) drawPick();
  }

  // The point of the questions: the current location, a saved point, or a new one (on the map or by coordinates).
  function togglePick() {
    var box = $('ask-pick');
    if (box.classList.contains('hidden')) { drawPick(); box.classList.remove('hidden'); } else box.classList.add('hidden');
  }
  function closePick() { $('ask-pick').classList.add('hidden'); }
  function drawPick() {
    var sel = C.selected();
    var pts = C.points().slice().reverse();
    $('ask-pick').innerHTML =
      '<button class="opt" data-pick="gps">◎ ' + esc(t('Mi ubicación actual (GPS)')) + '</button>' +
      (pts.length ? '<div class="pts">' + pts.map(function (p) {
        return '<button class="opt' + (p.id === sel ? ' on' : '') + '" data-pick="pt" data-id="' + esc(p.id) + '">' +
          (p.id === sel ? '✓ ' : '📍 ') + esc(p.name) + '<span class="muted small"> ' + p.lat.toFixed(4) + ', ' +
          p.lon.toFixed(4) + '</span></button>';
      }).join('') + '</div>' : '<div class="muted small">' + esc(t('Aún no hay puntos guardados.')) + '</div>') +
      '<div class="row wrap"><button class="small" data-pick="map">＋ ' + esc(t('Punto nuevo en el mapa')) + '</button>' +
      '<button class="small" data-pick="coords">＋ ' + esc(t('Por coordenadas')) + '</button></div>' +
      '<div id="ask-coords" class="row hidden"><input id="ask-lat" inputmode="decimal" placeholder="' + esc(t('Latitud')) +
      '"><input id="ask-lon" inputmode="decimal" placeholder="' + esc(t('Longitud')) + '">' +
      '<button class="small primary" data-pick="coords-ok">' + esc(t('Usar')) + '</button></div>';
  }
  function distance(a, b) {  // m
    var r = Math.PI / 180, x = (b.lon - a.lon) * r * Math.cos((a.lat + b.lat) / 2 * r), y = (b.lat - a.lat) * r;
    return Math.sqrt(x * x + y * y) * 6371000;
  }
  // the location of the GPS: the saved point at it (within its accuracy, or 20 m), else a new point
  function useLocation() {
    closePick();
    C.locate().then(function (loc) {
      var near = C.points().filter(function (p) { return distance(p, loc) <= Math.max(20, loc.accuracy || 0); })
        .sort(function (a, b) { return distance(a, loc) - distance(b, loc); })[0];
      var p = near || C.addPoint(t('Ubicación {0}', new Date().toLocaleString(i18n.locale,
        {day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'})), loc.lat, loc.lon);
      C.select(p.id);
    }, function () {});
  }
  function useCoords() {
    var lat = parseFloat(String($('ask-lat').value).replace(',', '.'));
    var lon = parseFloat(String($('ask-lon').value).replace(',', '.'));
    if (!(lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180)) return C.toast(t('Coordenadas no válidas (grados decimales WGS84)'));
    var p = C.addPoint(t('Punto {0}', C.points().length + 1), lat, lon);
    closePick();
    C.select(p.id);
  }
  $('ask-pick').onclick = function (ev) {
    var b = ev.target.closest('button[data-pick]');
    if (!b) return;
    var what = b.getAttribute('data-pick');
    if (what === 'gps') useLocation();
    else if (what === 'pt') { C.select(b.getAttribute('data-id')); closePick(); }
    else if (what === 'map') { closePick(); C.pickOnMap('ask'); }
    else if (what === 'coords') { $('ask-coords').classList.remove('hidden'); $('ask-lat').focus(); }
    else if (what === 'coords-ok') useCoords();
  };
  function autosize() {
    var t = $('ask-input');
    t.style.height = 'auto';
    t.style.height = Math.min(t.scrollHeight, 120) + 'px';
  }

  $('ask-send').onclick = function () { if (running) stop(); else send($('ask-input').value); };
  $('ask-input').addEventListener('input', autosize);
  $('ask-input').addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); $('ask-send').onclick(); }
  });
  $('ask-new').onclick = newChat;
  document.querySelector('nav button[data-tab=ask]').addEventListener('click', drawContext);
  document.addEventListener('campo:select', drawContext);

  // Ajustes: the model of the assistant -------------------------------------------------------------------------------

  var keys = {};
  function drawAiSettings() {
    var p = S.aiProvider, info = PROVIDERS[p];
    $('ai-provider').value = p;
    $('ai-key-box').classList.toggle('hidden', !info.key);
    $('ai-monitoreo-box').classList.toggle('hidden', info.key);
    if (info.key) {
      $('ai-key-state').textContent = keys[p] ? t('Clave guardada en el teléfono ({0}).', keys[p]) :
        t('Sin clave. Consíguela en {0}.', info.help);
      $('ai-key').value = '';
      $('ai-model').value = modelOf(p);
      $('ai-model').placeholder = info.model;
    }
    drawContext();
  }
  function loadKeys() {
    if (!window.Android) return Promise.resolve();
    return C.native('aiKeys').then(function (k) { keys = k || {}; }).catch(function () {});
  }
  $('ai-provider').onchange = function () {
    S.aiProvider = $('ai-provider').value;
    C.saveSettings();
    drawAiSettings();
  };
  $('ai-model').onchange = function () {
    var v = $('ai-model').value.trim();
    if (v && !/^[A-Za-z0-9._-]{1,80}$/.test(v)) { C.toast(t('Nombre de modelo no válido')); return; }
    S.aiModels[S.aiProvider] = v;
    C.saveSettings();
    drawContext();
  };
  $('ai-key-save').onclick = function () {
    var k = $('ai-key').value.trim();
    $('ai-key').value = '';
    if (!k) return C.toast(t('Pega la clave primero'));
    C.native('aiSetKey', {provider: S.aiProvider, key: k}).then(function (out) {
      keys = out;
      C.toast(t('Clave guardada en el teléfono'));
      drawAiSettings();
    }).catch(function (e) { C.toast(C.errText(e), 5000); });
  };
  $('ai-key-clear').onclick = function () {
    if (!confirm(t('¿Olvidar la clave de {0}?', PROVIDERS[S.aiProvider].name))) return;
    C.native('aiClearKey', S.aiProvider).then(function (out) { keys = out; drawAiSettings(); });
  };
  $('ai-test').onclick = function () {
    $('ai-test-state').textContent = t('Probando…');
    CHAT[S.aiProvider]([{role: 'system', content: 'Responde solo «ok».'}, {role: 'user', content: 'Di ok.'}], [])
      .then(function (m) {
        $('ai-test-state').textContent = t('Responde {0}: «{1}»', m.model || modelOf(S.aiProvider), String(m.content || '').slice(0, 60));
      }, function (e) { $('ai-test-state').textContent = t('Error: {0}', C.errText(e)); });
  };
  $('ai-provider').innerHTML = Object.keys(PROVIDERS).map(function (k) {
    return '<option value="' + k + '">' + esc(PROVIDERS[k].key ? t('{0} · tu clave', PROVIDERS[k].name) : t('{0} · gratis, sin clave', PROVIDERS[k].name)) + '</option>';
  }).join('');
  document.querySelector('nav button[data-tab=settings]').addEventListener('click', function () {
    loadKeys().then(drawAiSettings);
  });
  loadKeys().then(drawAiSettings);
  welcome();

  // for the tests in the browser (tools/test_ai.html)
  window.campoAI = {TOOLS: TOOLS, RUNNERS: RUNNERS, claudeParams: claudeParams, claudeAnswer: claudeAnswer,
    openaiAnswer: openaiAnswer, geminiSchema: geminiSchema, glmMessages: glmMessages, wireMessages: wireMessages,
    instructions: instructions, send: send, conv: function () { return conv; }, newChat: newChat, CHAT: CHAT};
})();
