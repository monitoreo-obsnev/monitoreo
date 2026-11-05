/*
 * The app of MonitorEO for the Earth Engine Code Editor and Earth Engine Apps: the interface over core.js, with the
 * options of the QGIS plugin (region, variable, period, season, comparison, pixel filters, map, time series, trends,
 * burn severity). Published as an app, it computes with the Cloud project of the app: whoever uses it needs no
 * account of Earth Engine. LIMITS keep each request within what a shared project can afford.
 */

(function () {
	var mo = MonitorEO;

	var LIMITS = {
		maxAreaKm2: 100000,   // the biggest region (km², all its polygons)
		s2AreaKm2: 5000,      // Sentinel-2 only for regions up to this size; bigger ones, Landsat or MODIS
		maxSteps: 400,        // steps of a time series (and of the series of the trends and comparisons)
		downloadBytes: 32e6   // size of a GeoTIFF (float32): bigger regions are downloaded with bigger pixels
	};

	var T = {
		es: {
			subtitle: 'Mapas, series y tendencias de variables de satélite (Sentinel-2, Landsat y MODIS) sobre ' +
				'áreas protegidas, ecorregiones o tu propia zona. Calcula en Google Earth Engine: no necesitas cuenta.',
			language: 'English',
			region: 'Región', mode_wdpa: 'Área protegida (WDPA)', mode_ecoregion: 'Ecorregión', mode_view: 'Vista del mapa',
			mode_draw: 'Polígono dibujado', search: 'Buscar', searchHint: 'Nombre, p. ej. Sierra Nevada',
			chooseArea: 'Elige el área', none: 'Ninguna área protegida con ese nombre.',
			clickHelp: 'Pulsa en el mapa sobre la ecorregión.', useView: 'Usar la vista del mapa',
			drawHelp: 'Dibuja un polígono en el mapa: un clic por vértice y doble clic para cerrarlo.',
			drawAgain: 'Dibujar otro', regionIs: 'Región: ', noRegion: 'Elige primero una región.',
			mapView: 'Vista del mapa', polygon: 'Polígono dibujado', loadingRegion: 'Cargando la región…',
			variable: 'Variable', period: 'Periodo (AAAA-MM-DD)', to: 'a', season: 'Solo esta temporada de cada año (MM-DD)',
			compare: 'Comparar con otro periodo', other: 'Otro periodo',
			filters: 'Quitar píxeles con', clouds: 'nubes y sombras', water: 'agua', snow: 'nieve', aerosols: 'aerosoles',
			cloudScore: 'nubes de Sentinel-2 con Cloud Score+ (si no, con la clasificación SCL)',
			conflict: 'Ojo: el filtro de %s quita lo que mide esta variable.',
			map: 'Mapa', metric: 'Métrica', temporal: 'Agregación temporal', t_period: 'Todo el periodo',
			t_annual: 'Cada año y entre años', t_monthly: 'Cada mes y entre años', 't_16-day': 'Cada 16 días y entre años',
			interannual: 'Métrica entre años', addMap: 'Añadir al mapa', download: 'Descargar GeoTIFF',
			downloadReady: 'GeoTIFF de %s m (NoData -9999): ', downloadLink: 'descargar',
			series: 'Serie temporal', step: 'Paso', s_daily: 'Diario (días con imágenes)', 's_16-day': '16 días',
			s_monthly: 'Mensual', s_annual: 'Anual', stepMetric: 'Métrica de cada paso', stat: 'Estadístico de la región',
			computeSeries: 'Calcular la serie temporal',
			trends: 'Tendencias (Mann-Kendall y Sen)', parts: 'Partes del año', p_monthly: 'Meses', 'p_16-day': '16 días',
			p_annual: 'El año', yearMetric: 'Métrica de cada año', trendTable: 'Tabla de tendencias',
			trendPart: 'Parte del año del mapa', output: 'Resultado', o_slope: 'Pendiente de Sen (por año)',
			o_tau: 'τ de Kendall', o_z: 'Z de Mann-Kendall', o_p_value: 'p-valor', o_intercept: 'Valor inicial',
			o_n: 'Años con datos', significant: 'Solo píxeles con tendencia significativa (p < 0,05)',
			trendMap: 'Mapa de tendencia', seeChart: 'Valores de cada año de',
			fire: 'Severidad de un incendio (dNBR o RBR)', sensor: 'Sensor', before: 'Antes del incendio',
			index: 'Índice', idx_dNBR: 'dNBR (clases del USGS)', idx_RBR: 'RBR (continuo, sin clases)',
			rbrNote: 'RBR = dNBR / (NBR antes + 1,001), con el NBR de B8A y B12 de Sentinel-2 (NIR y SWIR2 de ' +
				'Landsat), sin corrección fenológica y sin multiplicar por 1000.',
			after: 'Después del incendio', burn: 'Calcular la severidad',
			burned: 'Superficie quemada (dNBR ≥ 0,1): %s ha',
			about: 'Acerca de MonitorEO', manual: 'Manual', repository: 'Código', cite: 'Cómo citar',
			computing: 'Calculando…', progress: 'Calculando… %s de %s pasos', close: 'Cerrar', csv: 'Descargar CSV',
			chartHelp: 'El botón ⤢ de la gráfica la abre en otra pestaña, desde donde se descarga como imagen.',
			scaleNote: 'Calculado con píxeles de %s m.', date: 'Fecha', value: 'Valor', reference: 'Referencia',
			yearAxis: 'Año', senLine: 'recta de Sen', part: 'Parte del año', significantShort: 'signif.',
			yes: 'sí', no: 'no', klass: 'Clase', hectares: 'ha', dnbr: 'dNBR',
			tooBig: 'La región es demasiado grande para esta app (%s km²; máximo %s km²).',
			s2TooBig: 'Sentinel-2 solo está disponible para regiones de hasta %s km² (esta tiene %s): elige Landsat o MODIS.',
			tooManySteps: 'Son %s pasos (máximo %s): usa un paso más largo o un periodo más corto.',
			dailyCompare: 'Para comparar periodos o calcular tendencias, el paso no puede ser diario.',
			fewYears: 'Las tendencias necesitan un periodo de al menos dos años.',
			badDate: 'Fecha no válida: «%s». Usa AAAA-MM-DD (y MM-DD en la temporada).', error: 'Error: ',
			noData: 'No hay datos en ese periodo.',
			rangeNote: 'Colores con el rango del catálogo: Earth Engine no pudo calcular los percentiles 5 y 95 de la región.'
		},
		en: {
			subtitle: 'Maps, time series and trends of satellite variables (Sentinel-2, Landsat and MODIS) over ' +
				'protected areas, ecoregions or your own area. Computed in Google Earth Engine: no account needed.',
			language: 'Español',
			region: 'Region', mode_wdpa: 'Protected area (WDPA)', mode_ecoregion: 'Ecoregion', mode_view: 'Map view',
			mode_draw: 'Drawn polygon', search: 'Search', searchHint: 'Name, e.g. Sierra Nevada',
			chooseArea: 'Choose the area', none: 'No protected area with that name.',
			clickHelp: 'Click on the map over the ecoregion.', useView: 'Use the map view',
			drawHelp: 'Draw a polygon on the map: a click per vertex and a double click to close it.',
			drawAgain: 'Draw another', regionIs: 'Region: ', noRegion: 'Choose a region first.',
			mapView: 'Map view', polygon: 'Drawn polygon', loadingRegion: 'Loading the region…',
			variable: 'Variable', period: 'Period (YYYY-MM-DD)', to: 'to', season: 'Only this season of each year (MM-DD)',
			compare: 'Compare with another period', other: 'Other period',
			filters: 'Remove pixels with', clouds: 'clouds and shadows', water: 'water', snow: 'snow', aerosols: 'aerosols',
			cloudScore: 'Sentinel-2 clouds with Cloud Score+ (otherwise, with the SCL classification)',
			conflict: 'Note: the %s filter removes what this variable measures.',
			map: 'Map', metric: 'Metric', temporal: 'Temporal aggregation', t_period: 'Whole period',
			t_annual: 'Each year, then between years', t_monthly: 'Each month, then between years',
			't_16-day': 'Each 16 days, then between years', interannual: 'Metric between years', addMap: 'Add to the map',
			download: 'Download GeoTIFF', downloadReady: 'GeoTIFF of %s m (NoData -9999): ', downloadLink: 'download',
			series: 'Time series', step: 'Step', s_daily: 'Daily (days with images)', 's_16-day': '16 days',
			s_monthly: 'Monthly', s_annual: 'Annual', stepMetric: 'Metric of each step', stat: 'Statistic of the region',
			computeSeries: 'Compute the time series',
			trends: 'Trends (Mann-Kendall and Sen)', parts: 'Parts of the year', p_monthly: 'Months', 'p_16-day': '16 days',
			p_annual: 'The year', yearMetric: 'Metric of each year', trendTable: 'Trend table',
			trendPart: 'Part of the year of the map', output: 'Output', o_slope: 'Sen\'s slope (per year)',
			o_tau: 'Kendall\'s τ', o_z: 'Mann-Kendall Z', o_p_value: 'p-value', o_intercept: 'Initial value',
			o_n: 'Years with data', significant: 'Only pixels with a significant trend (p < 0.05)',
			trendMap: 'Trend map', seeChart: 'Values of each year of',
			fire: 'Burn severity of a fire (dNBR or RBR)', sensor: 'Sensor', before: 'Before the fire', after: 'After the fire',
			index: 'Index', idx_dNBR: 'dNBR (USGS classes)', idx_RBR: 'RBR (continuous, no classes)',
			rbrNote: 'RBR = dNBR / (NBR before + 1.001), with the NBR of B8A and B12 of Sentinel-2 (NIR and SWIR2 of ' +
				'Landsat), without phenological correction and without the factor 1000.',
			burn: 'Compute the severity', burned: 'Burned area (dNBR ≥ 0.1): %s ha',
			about: 'About MonitorEO', manual: 'Manual', repository: 'Code', cite: 'How to cite',
			computing: 'Computing…', progress: 'Computing… %s of %s steps', close: 'Close', csv: 'Download CSV',
			chartHelp: 'The ⤢ button of the chart opens it in another tab, where it can be downloaded as an image.',
			scaleNote: 'Computed on pixels of %s m.', date: 'Date', value: 'Value', reference: 'Reference',
			yearAxis: 'Year', senLine: 'Sen line', part: 'Part of the year', significantShort: 'signif.',
			yes: 'yes', no: 'no', klass: 'Class', hectares: 'ha', dnbr: 'dNBR',
			tooBig: 'The region is too big for this app (%s km²; at most %s km²).',
			s2TooBig: 'Sentinel-2 is only available for regions up to %s km² (this one has %s): choose Landsat or MODIS.',
			tooManySteps: '%s steps (at most %s): use a longer step or a shorter period.',
			dailyCompare: 'To compare periods or compute trends, the step cannot be daily.',
			fewYears: 'Trends need a period of at least two years.',
			badDate: 'Not a valid date: "%s". Use YYYY-MM-DD (and MM-DD for the season).', error: 'Error: ',
			noData: 'No data in that period.',
			rangeNote: 'Colours with the range of the catalog: Earth Engine could not compute the percentiles 5 and 95 of the region.'
		}
	};

	var METRICS = ['mean', 'median', 'min', 'max', 'p5', 'p10', 'p25', 'p75', 'p90', 'p95', 'std', 'count'];
	var STATS = ['mean', 'median', 'min', 'max', 'std', 'p5', 'p10', 'p25', 'p75', 'p90', 'p95'];
	var METRIC_NAMES = {
		es: {mean: 'Media', median: 'Mediana', min: 'Mínimo', max: 'Máximo', std: 'Desviación típica', count: 'Número',
			sum: 'Suma'},
		en: {mean: 'Mean', median: 'Median', min: 'Minimum', max: 'Maximum', std: 'Standard deviation', count: 'Count',
			sum: 'Sum'}
	};

	var state = {
		lang: 'en', mode: 'wdpa', wdpaText: 'Sierra Nevada', wdpaItems: null, wdpaNames: {}, wdpaId: null,
		region: null, regionName: null, info: null,
		ref: 27, period: ['2025-01-01', '2025-12-31'], seasonOn: false, season: ['06-01', '08-31'],
		compareOn: false, other: ['2020-01-01', '2020-12-31'],
		quality: {clouds: true, water: true, snow: true, aerosols: true, cloud_score: 0.6},
		mapMetric: 'median', temporal: 'period', interannual: 'mean',
		step: 'monthly', stepMetric: 'mean', stat: 'mean',
		trendStep: 'monthly', trendMetric: 'mean', trendPart: 7, output: 'slope', significant: false,
		fireSensor: 'Sentinel-2', fireBefore: ['2025-06-01', '2025-07-31'], fireAfter: ['2025-09-01', '2025-10-31'],
		fireIndex: 'dNBR'
	};
	var run = 0;  // number of the last computation: the answers of older ones are left out

	function t(key) {
		return T[state.lang][key];
	}

	function fmt(text) {
		var args = Array.prototype.slice.call(arguments, 1);
		return text.replace(/%s/g, function () { return String(args.shift()); });
	}

	function num(x, digits) {
		if (x === null || x === undefined) return '';
		var s = Math.abs(x) >= 1000 || x === Math.round(x) ? String(Math.round(x * 100) / 100) :
			Number(x).toPrecision(digits || 4);
		return state.lang === 'es' ? s.replace('.', ',') : s;
	}

	function bigNum(x) {
		var s = String(Math.round(x)).replace(/\B(?=(\d{3})+(?!\d))/g, state.lang === 'es' ? '.' : ',');
		return s;
	}

	function metricName(m) {
		return METRIC_NAMES[state.lang][m] || (m.charAt(0) === 'p' ? (state.lang === 'es' ? 'Percentil ' : 'Percentile ') +
			m.slice(1) : m);
	}

	// Map, panels and legend --------------------------------------------------------------------------------------

	var map = ui.Map();
	map.setOptions('HYBRID');
	map.setCenter(-3.3, 37.05, 9);
	map.style().set('cursor', 'crosshair');
	var drawing = map.drawingTools();
	drawing.setShown(false);
	drawing.setLinked(false);
	drawing.setDrawModes(['polygon']);
	var controls = ui.Panel({style: {width: '380px', padding: '4px 10px'}});
	var results = ui.Panel({style: {width: '460px', padding: '4px 10px', shown: false}});
	var legend = ui.Panel({style: {position: 'bottom-left', padding: '6px 8px', shown: false}});
	map.add(legend);
	ui.root.clear();
	ui.root.setLayout(ui.Panel.Layout.flow('horizontal'));
	ui.root.add(controls);
	ui.root.add(map);
	ui.root.add(results);
	var regionLayer = null;

	var H = {fontWeight: 'bold', fontSize: '14px', margin: '14px 0 4px 8px'};
	var SMALL = {fontSize: '12px', color: '#555'};

	function header(text) {
		return ui.Label(text, H);
	}

	function row() {
		return ui.Panel(Array.prototype.slice.call(arguments), ui.Panel.Layout.flow('horizontal'));
	}

	function box(value, onChange, width) {
		return ui.Textbox({value: value, onChange: onChange, style: {width: width || '100px'}});
	}

	function select(items, value, onChange, width) {
		return ui.Select({items: items, value: value, onChange: onChange, style: {width: width || '160px'}});
	}

	function check(label, value, onChange) {
		return ui.Checkbox({label: label, value: value, onChange: onChange});
	}

	function button(label, onClick) {
		return ui.Button({label: label, onClick: onClick});
	}

	// Results: a panel to the right of the map, with the answer of the last computation
	function show(widgets) {
		results.clear();
		results.add(row(ui.Label('MonitorEO', {fontWeight: 'bold', fontSize: '16px', stretch: 'horizontal'}),
			button(t('close'), function () { results.style().set('shown', false); })));
		widgets.forEach(function (w) { results.add(w); });
		results.style().set('shown', true);
	}

	function message(text, error) {
		show([ui.Label(text, {color: error ? '#b00020' : '#333', whiteSpace: 'pre-wrap'})]);
	}

	function fail(error) {
		message(t('error') + error, true);
	}

	function start() {
		run += 1;
		message(t('computing'));
		return run;
	}

	function colourBar(vis, title) {
		legend.clear();
		legend.add(ui.Label(title, {fontWeight: 'bold', fontSize: '12px', margin: '0 0 4px 0'}));
		legend.add(ui.Thumbnail({image: ee.Image.pixelLonLat().select(0), params: {bbox: [0, 0, 1, 0.1],
			dimensions: '200x12', format: 'png', min: 0, max: 1, palette: vis.palette}, style: {margin: '0'}}));
		legend.add(row(ui.Label(num(vis.min), {fontSize: '11px', margin: '0'}),
			ui.Label(num(vis.max), {fontSize: '11px', margin: '0 0 0 150px'})));
		legend.style().set('shown', true);
	}

	function classLegend(title, names, colours) {
		legend.clear();
		legend.add(ui.Label(title, {fontWeight: 'bold', fontSize: '12px', margin: '0 0 4px 0'}));
		names.forEach(function (name, i) {
			legend.add(row(ui.Label('', {backgroundColor: '#' + colours[i], padding: '7px', margin: '2px 6px 2px 0'}),
				ui.Label(name, {fontSize: '11px', margin: '2px 0'})));
		});
		legend.style().set('shown', true);
	}

	// Region --------------------------------------------------------------------------------------------------------

	function setRegion(fc, name) {
		state.region = fc;
		state.regionName = name;
		state.info = null;
		if (regionLayer) map.layers().remove(regionLayer);
		regionLayer = map.addLayer(ee.FeatureCollection(fc).style({color: 'ffff00', fillColor: '00000000', width: 2}), {},
			name);
		ee.Dictionary({info: mo.regionInfo(fc), n: fc.size()}).evaluate(function (d, error) {
			if (error) return fail(error);
			if (state.region !== fc) return;
			state.info = d.info;
			state.info.n = d.n;
			state.info.crs = mo.utmOf(d.info.centroid[0], d.info.centroid[1]);
			render();
		});
		fc.geometry().bounds(1000).evaluate(function (b) {
			if (b && state.region === fc) map.centerObject(ee.Geometry(b));
		});
		render();
	}

	function km2(m2) {
		return m2 / 1e6;
	}

	map.onClick(function (coords) {
		if (state.mode !== 'ecoregion') return;
		var fc = mo.ecoregionAt(coords.lon, coords.lat);
		fc.aggregate_array('name').evaluate(function (names, error) {
			if (error) return fail(error);
			if (names && names.length) setRegion(fc, names[0]);
		});
	});

	drawing.onDraw(function (geometry) {
		if (state.mode !== 'draw') return;
		drawing.setShape(null);
		setRegion(ee.FeatureCollection([ee.Feature(geometry, {name: t('polygon')})]), t('polygon'));
	});

	function searchWdpa() {
		state.wdpaItems = null;
		message(t('computing'));
		mo.findProtectedAreas(state.wdpaText, 30).evaluate(function (fc, error) {
			if (error) return fail(error);
			state.wdpaNames = {};
			state.wdpaItems = fc.features.map(function (f) {
				var p = f.properties;
				var desig = state.lang === 'en' ? p.DESIG_ENG : p.DESIG;
				state.wdpaNames[p.SITE_ID] = p.NAME + ' · ' + desig;
				return {value: p.SITE_ID, label: [p.NAME, desig, p.ISO3, (p.REP_AREA < 10 ? num(p.REP_AREA, 2) :
					bigNum(p.REP_AREA)) + ' km²'].join(' · ') + ' (WDPA ' + p.SITE_ID + ')'};
			});
			results.style().set('shown', false);
			if (!state.wdpaItems.length) message(t('none'));
			render();
		});
	}

	function chooseWdpa(id) {
		state.wdpaId = id;
		var label = state.wdpaNames[id];
		message(t('loadingRegion'));
		mo.wdpaGeometries([id]).evaluate(function (info, error) {
			if (error) return fail(error);
			results.style().set('shown', false);
			setRegion(mo.wdpaRegion(info), label);
		});
	}

	function regionWidgets() {
		var w = [header(t('region'))];
		var modes = ['wdpa', 'ecoregion', 'view', 'draw'].map(function (m) { return {value: m, label: t('mode_' + m)}; });
		w.push(select(modes, state.mode, function (m) {
			state.mode = m;
			drawing.setShown(m === 'draw');
			if (m === 'draw') drawing.setShape('polygon');
			render();
		}, '250px'));
		if (state.mode === 'wdpa') {
			var text = ui.Textbox({placeholder: t('searchHint'), value: state.wdpaText,
				onChange: function (v) { state.wdpaText = v; }, style: {width: '200px'}});
			w.push(row(text, button(t('search'), function () {
				state.wdpaText = text.getValue();
				searchWdpa();
			})));
			if (state.wdpaItems && state.wdpaItems.length) {
				w.push(ui.Select({items: state.wdpaItems, placeholder: t('chooseArea'), value: state.wdpaId,
					onChange: chooseWdpa, style: {width: '340px'}}));
			}
		} else if (state.mode === 'ecoregion') {
			w.push(ui.Label(t('clickHelp'), SMALL));
		} else if (state.mode === 'view') {
			w.push(button(t('useView'), function () {
				var b = map.getBounds();
				setRegion(mo.bboxRegion(b, t('mapView')), t('mapView'));
			}));
		} else {
			w.push(ui.Label(t('drawHelp'), SMALL));
			w.push(button(t('drawAgain'), function () {
				drawing.layers().reset();
				drawing.setShape('polygon');
			}));
		}
		if (state.region) {
			var area = state.info ? ' · ' + bigNum(km2(state.info.total)) + ' km²' : '';
			w.push(ui.Label(t('regionIs') + state.regionName + area, {fontSize: '12px', color: '#1a73e8'}));
		}
		return w;
	}

	// Variable, period, filters -------------------------------------------------------------------------------------

	function entry() {
		return mo.byRef(state.ref);
	}

	function variableItems() {  // without RBR, which compares two periods (Burn severity)
		return mo.variables().filter(function (e) { return !e.two_periods; }).sort(function (a, b) {
			return a.index < b.index ? -1 : a.index > b.index ? 1 : a.sensor < b.sensor ? -1 : a.sensor > b.sensor ? 1 :
				a.ref - b.ref;
		}).map(function (e) {
			return {value: e.ref, label: [e.index, e.sensor, e.m + ' m', e.col.split('/').pop()].join(' · ')};
		});
	}

	function setVariable(ref) {
		state.ref = ref;
		var e = entry();
		mo.FILTERS.forEach(function (f) { state.quality[f] = (mo.MEASURES[f] || []).indexOf(e.index) < 0; });
		render();
	}

	function variableWidgets() {
		var e = entry();
		var w = [header(t('variable')), select(variableItems(), state.ref, setVariable, '340px')];
		var name = state.lang === 'en' ? e.vname_en : e.vname;
		w.push(ui.Label([name, e.unit, (state.lang === 'en' ? 'pixel ' : 'píxel ') + e.m + ' m', e.dr, e.ft]
			.filter(function (x) { return x; }).join(' · '), SMALL));
		w.push(header(t('period')));
		w.push(row(box(state.period[0], function (v) { state.period[0] = v.trim(); }), ui.Label(t('to')),
			box(state.period[1], function (v) { state.period[1] = v.trim(); })));
		w.push(check(t('season'), state.seasonOn, function (v) {
			state.seasonOn = v;
			render();
		}));
		if (state.seasonOn) {
			w.push(row(box(state.season[0], function (v) { state.season[0] = v.trim(); }, '70px'), ui.Label(t('to')),
				box(state.season[1], function (v) { state.season[1] = v.trim(); }, '70px')));
		}
		w.push(check(t('compare'), state.compareOn, function (v) {
			state.compareOn = v;
			render();
		}));
		if (state.compareOn) {
			w.push(row(ui.Label(t('other') + ':'), box(state.other[0], function (v) { state.other[0] = v.trim(); }),
				ui.Label(t('to')), box(state.other[1], function (v) { state.other[1] = v.trim(); })));
		}
		w.push(header(t('filters')));
		var available = mo.filters(e, {clouds: true, water: true, snow: true, aerosols: true});
		mo.FILTERS.forEach(function (f) {
			var c = check(t(f), state.quality[f] && available[f], function (v) {
				state.quality[f] = v;
				render();
			});
			c.setDisabled(!available[f]);
			w.push(c);
		});
		if (e.sensor === 'Sentinel-2') {
			w.push(check(t('cloudScore'), state.quality.cloud_score !== null, function (v) {
				state.quality.cloud_score = v ? 0.6 : null;
			}));
		}
		mo.conflicts(e, state.quality).forEach(function (f) {
			w.push(ui.Label(fmt(t('conflict'), t(f)), {fontSize: '12px', color: '#b06000'}));
		});
		return w;
	}

	// Checks and specs ----------------------------------------------------------------------------------------------

	var DATE = /^\d{4}-\d{2}-\d{2}$/;
	var MONTH_DAY = /^\d{2}-\d{2}$/;

	function checkPeriod(p) {
		p.forEach(function (d) {
			if (!DATE.test(d) || isNaN(mo.date(d).getTime())) throw new Error(fmt(t('badDate'), d));
		});
	}

	// The spec of the variable over PERIOD (default: the period), or an Error with what is wrong
	function specOf(period, metric, ref) {
		period = period || state.period;
		checkPeriod(period);
		var season = null;
		if (state.seasonOn) {
			state.season.forEach(function (d) { if (!MONTH_DAY.test(d)) throw new Error(fmt(t('badDate'), d)); });
			season = state.season.slice();
		}
		var s = mo.spec({ref: ref || state.ref, period: period.slice(), season: season, quality: state.quality,
			metric: metric || 'mean'});
		mo.windows(s.period, s.season);
		return s;
	}

	// The region checked for the entry E: true, or false after showing why not
	function ready(e) {
		if (!state.region || !state.info) {
			message(t('noRegion'), true);
			return false;
		}
		var area = km2(state.info.total);
		if (area > LIMITS.maxAreaKm2) {
			message(fmt(t('tooBig'), bigNum(area), bigNum(LIMITS.maxAreaKm2)), true);
			return false;
		}
		if (e.sensor === 'Sentinel-2' && area > LIMITS.s2AreaKm2) {
			message(fmt(t('s2TooBig'), bigNum(LIMITS.s2AreaKm2), bigNum(area)), true);
			return false;
		}
		return true;
	}

	function guarded(f) {
		return function () {
			try {
				f();
			} catch (e) {
				message(e.message || String(e), true);
			}
		};
	}

	function title(e, extra) {
		return [e.index + ' ' + e.sensor, state.regionName].concat(extra || []).join(' · ');
	}

	// Download of an image of the region as GeoTIFF (float, NoData -9999), with pixels as small as LIMITS allow
	function downloadWidget(img, e, bands, name) {
		var panel = ui.Panel();
		panel.add(button(t('download'), function () {
			var native = Number(e.m);
			var pixels = state.info.boundsArea / (native * native);
			var maxPixels = LIMITS.downloadBytes / (4 * bands.length);
			var scale = native * Math.max(1, Math.ceil(Math.sqrt(pixels / maxPixels)));
			panel.clear();
			panel.add(ui.Label(t('computing'), SMALL));
			ee.Image(img).select(bands).toFloat().unmask(-9999, false).getDownloadURL({
				name: name.replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 90), region: state.region.geometry().bounds(1000),
				scale: scale, crs: state.info.crs, format: 'GEO_TIFF', filePerBand: false
			}, function (url, error) {
				panel.clear();
				if (error) return panel.add(ui.Label(t('error') + error, {color: '#b00020'}));
				panel.add(row(ui.Label(fmt(t('downloadReady'), num(scale)), SMALL),
					ui.Label(t('downloadLink'), {fontSize: '12px'}, url)));
			});
		}));
		return panel;
	}

	// CSV of ROWS (their COLUMNS) as a download link of Earth Engine
	function csvWidget(rows, columns, name) {
		var panel = ui.Panel();
		panel.add(button(t('csv'), function () {
			panel.clear();
			panel.add(ui.Label(t('computing'), SMALL));
			ee.FeatureCollection(rows.map(function (r) {
				var p = {};
				columns.forEach(function (c) { p[c] = r[c] === null || r[c] === undefined ? '' : r[c]; });
				return ee.Feature(null, p);
			})).getDownloadURL('CSV', columns, name.replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 90), function (url, error) {
				panel.clear();
				if (error) return panel.add(ui.Label(t('error') + error, {color: '#b00020'}));
				panel.add(ui.Label(t('csv') + ' ↓', {fontSize: '12px'}, url));
			});
		}));
		return panel;
	}

	// Pixel size of the percentiles of the colour ramp: about 250 000 pixels over the bounds of the region
	function rangeScale(e) {
		return Math.max(Number(e.m), mo.autoScale(e, state.info.boundsArea * 4));
	}

	// Map -----------------------------------------------------------------------------------------------------------

	function addMap() {
		var e = entry();
		if (!ready(e)) return;
		var s = specOf(null, state.mapMetric);
		s.temporal = state.temporal;
		s.interannual = state.interannual;
		var geom = state.region.geometry();
		var img, name;
		if (state.compareOn) {
			var o = specOf(state.other, state.mapMetric);
			o.temporal = s.temporal;
			o.interannual = s.interannual;
			img = mo.comparisonImage(s, o, geom).clipToCollection(state.region);
			name = title(e, [metricName(state.mapMetric), o.period.join('/') + ' − ' + s.period.join('/')]);
		} else {
			img = mo.image(s, geom).clipToCollection(state.region);
			name = title(e, [metricName(state.mapMetric), s.period.join('/')]);
		}
		var id = start();
		var band = state.compareOn ? img.select('difference') : img;
		mo.percentiles(band, geom, rangeScale(e)).evaluate(function (stats, error) {
			if (id !== run) return;
			var vis;
			if (error) {  // the range of the catalog
				var span = typeof e.minp === 'number' && typeof e.maxp === 'number' ? (e.maxp - e.minp) / 4 : 0.1;
				vis = state.compareOn ? {min: -span, max: span, palette: mo.DIVERGING} : mo.visParams(null, e);
			} else {
				vis = state.compareOn ? mo.trendVis('difference', stats.value_p5, stats.value_p95) : mo.visParams(stats, e);
			}
			map.addLayer(band, vis, name);
			colourBar(vis, name + (e.unit ? ' ' + e.unit : ''));
			var widgets = [ui.Label(name, {fontWeight: 'bold'})];
			if (error) widgets.push(ui.Label(t('rangeNote'), SMALL));
			widgets.push(downloadWidget(img, e, state.compareOn ? ['difference', 'reference', 'other'] : ['value'], name));
			show(widgets);
		});
	}

	function mapWidgets() {
		var w = [header(t('map'))];
		var metrics = METRICS.map(function (m) { return {value: m, label: metricName(m)}; });
		w.push(row(ui.Label(t('metric')), select(metrics, state.mapMetric, function (v) { state.mapMetric = v; })));
		var temporal = mo.TEMPORAL.map(function (x) { return {value: x, label: t('t_' + x)}; });
		w.push(row(ui.Label(t('temporal')), select(temporal, state.temporal, function (v) {
			state.temporal = v;
			render();
		}, '190px')));
		if (state.temporal !== 'period') {
			w.push(row(ui.Label(t('interannual')), select(metrics, state.interannual, function (v) {
				state.interannual = v;
			})));
		}
		w.push(button(t('addMap'), guarded(addMap)));
		return w;
	}

	// Time series and comparison of periods -------------------------------------------------------------------------

	function dateCell(d) {
		var p = d.split('-');
		return 'Date(' + Number(p[0]) + ', ' + (Number(p[1]) - 1) + ', ' + Number(p[2]) + ')';
	}

	function regionsOf(rows) {
		var out = [];
		rows.forEach(function (r) { if (out.indexOf(r.region) < 0) out.push(r.region); });
		return out;
	}

	function seriesChart(rows, e, name) {
		var regions = regionsOf(rows);
		var dates = [];
		var values = {};
		rows.forEach(function (r) {
			if (dates.indexOf(r.date) < 0) dates.push(r.date);
			values[r.region + '|' + r.date] = r.value;
		});
		dates.sort();
		var cols = [{id: 'date', label: t('date'), type: 'date'}].concat(regions.map(function (g, i) {
			return {id: 'r' + i, label: g, type: 'number'};
		}));
		var data = dates.map(function (d) {
			return {c: [{v: dateCell(d)}].concat(regions.map(function (g) {
				var v = values[g + '|' + d];
				return {v: v === undefined ? null : v};
			}))};
		});
		return ui.Chart({cols: cols, rows: data}, 'LineChart', {title: name, vAxis: {title: e.unit}, lineWidth: 1.5,
			pointSize: 3, interpolateNulls: false, legend: {position: regions.length > 1 ? 'right' : 'none'}});
	}

	// The time series of S (or, with PARTS, the values of each part of the year in each year: trends and comparisons):
	// done(rows, scale)
	function fetchSeries(s, metric, steps, id, done) {
		if (steps.length > LIMITS.maxSteps) throw new Error(fmt(t('tooManySteps'), steps.length, LIMITS.maxSteps));
		var scale = mo.autoScale(mo.entryOf(s), state.info.area);
		mo.series(s, state.region, state.info.n, metric, state.stat, scale, state.info.crs, steps, function (error, rows) {
			if (id !== run) return;
			if (error) return fail(error);
			done(rows, scale);
		}, function (k, n) {
			if (id === run) message(fmt(t('progress'), k, n));
		});
	}

	function computeSeries() {
		var e = entry();
		if (!ready(e)) return;
		if (state.compareOn) return compareSeries();
		var s = specOf();
		var name = title(e, [metricName(state.stepMetric) + ' ' + t('s_' + state.step).toLowerCase(),
			metricName(state.stat).toLowerCase()]);
		var id = start();
		function go(steps) {
			fetchSeries(s, state.stepMetric, steps, id, function (rows, scale) {
				if (!rows.some(function (r) { return r.value !== null; })) return message(t('noData'), true);
				show([seriesChart(rows, e, name), ui.Label(fmt(t('scaleNote'), num(scale)) + ' ' + t('chartHelp'), SMALL),
					csvWidget(rows, ['region', 'date', 'value', 'n_pixels', 'n_images'], name)]);
			});
		}
		if (state.step !== 'daily') return go(mo.seriesBins(s, state.step));
		mo.dailyDays(s, state.region.geometry()).evaluate(guardedAsync(id, function (days) {
			go(mo.dailyBins(days));
		}));
	}

	function guardedAsync(id, f) {
		return function (value, error) {
			if (id !== run) return;
			if (error) return fail(error);
			try {
				f(value);
			} catch (e) {
				message(e.message || String(e), true);
			}
		};
	}

	// Values of each part of the year in each year of S: done(rows with part and year, scale)
	function seasonalSeries(s, step, metric, id, done) {
		if (step === 'daily') throw new Error(t('dailyCompare'));
		var sbins = mo.seasonalBins(s, step);
		fetchSeries(s, metric, sbins.map(function (b) { return [b[2], b[3]]; }), id, function (rows, scale) {
			done(mo.withParts(rows, sbins), scale);
		});
	}

	function partName(step, part) {
		var label = mo.partLabel(step, part, state.lang);
		return step === 'monthly' ? label.slice(0, 3) : step === '16-day' ? mo.partKey(step, part) : label;
	}

	function compareSeries() {
		var e = entry();
		var a = specOf(), b = specOf(state.other);
		var step = state.step;
		var names = [a.period, b.period].map(function (p) {
			return p[0].slice(0, 4) === p[1].slice(0, 4) ? p[0].slice(0, 4) : p[0].slice(0, 4) + '-' + p[1].slice(0, 4);
		});
		var name = title(e, [names[0] + ' / ' + names[1], metricName(state.stepMetric).toLowerCase()]);
		var id = start();
		seasonalSeries(a, step, state.stepMetric, id, function (ra, scale) {
			seasonalSeries(b, step, state.stepMetric, id, function (rb) {
				var prof = mo.profile(ra, rb);
				prof.forEach(function (r) {
					r.key = mo.partKey(step, r.part);
					r.label = mo.partLabel(step, r.part, state.lang);
				});
				var regions = regionsOf(prof);
				var parts = mo.parts(step);
				var cols = [{id: 'part', label: t('part'), type: 'string'}];
				regions.forEach(function (g, i) {
					var prefix = regions.length > 1 ? g + ' ' : '';
					cols.push({id: 'a' + i, label: prefix + names[0], type: 'number'});
					cols.push({id: 'b' + i, label: prefix + names[1], type: 'number'});
				});
				var byKey = {};
				prof.forEach(function (r) { byKey[r.region + '|' + r.part] = r; });
				var data = parts.map(function (p) {
					var c = [{v: partName(step, p)}];
					regions.forEach(function (g) {
						var r = byKey[g + '|' + p] || {};
						c.push({v: r.reference === undefined ? null : r.reference});
						c.push({v: r.other === undefined ? null : r.other});
					});
					return {c: c};
				});
				var series = {};
				regions.forEach(function (g, i) {
					series[2 * i] = {color: regions.length > 1 ? undefined : '#1f77b4', pointShape: 'circle'};
					series[2 * i + 1] = {color: regions.length > 1 ? undefined : '#d62728', lineDashStyle: [6, 3],
						pointShape: 'square'};
				});
				var chart = ui.Chart({cols: cols, rows: data}, 'LineChart', {title: name, vAxis: {title: e.unit},
					pointSize: 4, lineWidth: 1.5, series: series});
				show([chart, ui.Label(fmt(t('scaleNote'), num(scale)), SMALL), csvWidget(prof,
					['region', 'key', 'label', 'reference', 'other', 'difference', 'n_reference', 'n_other'], name)]);
			});
		});
	}

	function seriesWidgets() {
		var w = [header(t('series'))];
		var steps = mo.STEPS.map(function (x) { return {value: x, label: t('s_' + x)}; });
		w.push(row(ui.Label(t('step')), select(steps, state.step, function (v) { state.step = v; })));
		var metrics = METRICS.map(function (m) { return {value: m, label: metricName(m)}; });
		w.push(row(ui.Label(t('stepMetric')), select(metrics, state.stepMetric, function (v) { state.stepMetric = v; })));
		var stats = STATS.map(function (m) { return {value: m, label: metricName(m)}; });
		w.push(row(ui.Label(t('stat')), select(stats, state.stat, function (v) { state.stat = v; })));
		w.push(button(t('computeSeries'), guarded(computeSeries)));
		return w;
	}

	// Trends --------------------------------------------------------------------------------------------------------

	function enoughYears(s) {
		if (mo.windows(s.period, s.season).length < 2) throw new Error(t('fewYears'));
	}

	function trendChart(yearly, rows, step, part, e) {
		var regions = regionsOf(rows);
		var years = [];
		yearly.forEach(function (r) { if (r.part === part && years.indexOf(r.year) < 0) years.push(r.year); });
		years.sort();
		var cols = [{id: 'year', label: t('yearAxis'), type: 'number'}];
		var series = {};
		regions.forEach(function (g, i) {
			cols.push({id: 'v' + i, label: g, type: 'number'});
			cols.push({id: 's' + i, label: g + ' (' + t('senLine') + ')', type: 'number'});
			series[2 * i] = {pointSize: 5, lineWidth: 0};
			series[2 * i + 1] = {pointSize: 0, lineWidth: 2, visibleInLegend: false};
		});
		var value = {}, trend = {};
		yearly.forEach(function (r) { if (r.part === part) value[r.region + '|' + r.year] = r.value; });
		rows.forEach(function (r) { if (r.part === part) trend[r.region] = r; });
		var first = years.length ? years[0] : 0;
		var data = years.map(function (y) {
			var c = [{v: y}];
			regions.forEach(function (g) {
				var v = value[g + '|' + y], tr = trend[g];
				c.push({v: v === undefined ? null : v});
				c.push({v: tr && tr.slope !== null ? tr.intercept + tr.slope * (y - first) : null});
			});
			return {c: c};
		});
		return ui.Chart({cols: cols, rows: data}, 'LineChart', {title: t('seeChart') + ' ' +
			mo.partLabel(step, part, state.lang), vAxis: {title: e.unit}, hAxis: {format: '####'}, series: series,
			legend: {position: regions.length > 1 ? 'right' : 'none'}});
	}

	function trendTable() {
		var e = entry();
		if (!ready(e)) return;
		var s = specOf();
		enoughYears(s);
		var step = state.trendStep;
		var first = mo.windows(s.period, s.season)[0][0];
		var name = title(e, [t('trends'), metricName(state.trendMetric).toLowerCase()]);
		var id = start();
		seasonalSeries(s, step, state.trendMetric, id, function (yearly, scale) {
			var rows = mo.trendRows(yearly, step, first, state.lang);
			var cols = [t('part'), 'n', 'τ', 'Z', 'p', t('significantShort'), e.unit ? 'Sen (' + e.unit + '/' +
				(state.lang === 'es' ? 'año' : 'year') + ')' : 'Sen'];
			var regions = regionsOf(rows);
			if (regions.length > 1) cols.unshift(t('region'));
			var table = [cols].concat(rows.map(function (r) {
				var c = [r.label, r.n, num(r.tau, 3), num(r.z, 3), num(r.p_value, 3), r.significant ? t('yes') : t('no'),
					num(r.slope, 3)];
				if (regions.length > 1) c.unshift(r.region);
				return c;
			}));
			var chartPanel = ui.Panel();
			var parts = mo.parts(step);
			function showPart(p) {
				chartPanel.clear();
				chartPanel.add(trendChart(yearly, rows, step, p, e));
			}
			var widgets = [ui.Label(name, {fontWeight: 'bold'}), ui.Chart(table, 'Table', {allowHtml: false})];
			if (parts.length > 1) {
				widgets.push(row(ui.Label(t('seeChart')), select(parts.map(function (p) {
					return {value: p, label: mo.partLabel(step, p, state.lang)};
				}), parts[0], showPart)));
			}
			widgets.push(chartPanel);
			widgets.push(ui.Label(fmt(t('scaleNote'), num(scale)), SMALL));
			widgets.push(csvWidget(rows, ['region', 'key', 'label', 'n', 'tau', 'z', 'p_value', 'significant', 'slope',
				'intercept', 'first_year', 'last_year'], name));
			show(widgets);
			showPart(parts[0]);
		});
	}

	function trendMap() {
		var e = entry();
		if (!ready(e)) return;
		var s = specOf();
		enoughYears(s);
		var step = state.trendStep;
		var part = step === 'annual' ? 0 : state.trendPart;
		if (step === '16-day' && part > 23) part = 23;
		var geom = state.region.geometry();
		var img = mo.trendImage(s, geom, step, part, state.trendMetric);
		if (state.significant) img = img.updateMask(img.select('p_value').lt(0.05));
		img = img.clipToCollection(state.region);
		var output = state.output;
		var band = img.select(output);
		var name = title(e, [mo.partLabel(step, part, state.lang), t('o_' + output)]);
		var unit = output === 'slope' ? e.unit + ' / ' + (state.lang === 'es' ? 'año' : 'year') :
			output === 'intercept' ? e.unit : '';
		var id = start();
		function add(vis) {
			map.addLayer(band, vis, name);
			colourBar(vis, name + (unit ? ' ' + unit : ''));
			show([ui.Label(name, {fontWeight: 'bold'}), downloadWidget(img, e, mo.OUTPUTS, name)]);
		}
		var fixed = mo.trendVis(output);
		if (fixed && output !== 'slope' && output !== 'z' && output !== 'n') return add(fixed);
		mo.percentiles(band, geom, rangeScale(e)).evaluate(guardedAsync(id, function (stats) {
			var auto = mo.visParams(stats, e);
			add(mo.trendVis(output, auto.min, auto.max) || auto);
		}));
	}

	function trendWidgets() {
		var w = [header(t('trends'))];
		var steps = mo.TREND_STEPS.map(function (x) { return {value: x, label: t('p_' + x)}; });
		w.push(row(ui.Label(t('parts')), select(steps, state.trendStep, function (v) {
			state.trendStep = v;
			render();
		})));
		var metrics = METRICS.map(function (m) { return {value: m, label: metricName(m)}; });
		w.push(row(ui.Label(t('yearMetric')), select(metrics, state.trendMetric, function (v) { state.trendMetric = v; })));
		w.push(button(t('trendTable'), guarded(trendTable)));
		if (state.trendStep !== 'annual') {
			var parts = mo.parts(state.trendStep).map(function (p) {
				return {value: p, label: mo.partLabel(state.trendStep, p, state.lang)};
			});
			if (state.trendPart > parts.length) state.trendPart = 1;
			w.push(row(ui.Label(t('trendPart')), select(parts, state.trendPart, function (v) { state.trendPart = v; })));
		}
		var outputs = mo.OUTPUTS.map(function (o) { return {value: o, label: t('o_' + o)}; });
		w.push(row(ui.Label(t('output')), select(outputs, state.output, function (v) { state.output = v; }, '190px')));
		w.push(check(t('significant'), state.significant, function (v) { state.significant = v; }));
		w.push(button(t('trendMap'), guarded(trendMap)));
		return w;
	}

	// Burn severity -------------------------------------------------------------------------------------------------

	// RBR: a continuous map of red (burned) to green (regrowth), its statistics over each region and its GeoTIFF
	function burnRatio() {
		var ref = state.fireSensor === 'Landsat' ? 104 : 103;
		var e = mo.byRef(ref);
		if (!ready(e)) return;
		checkPeriod(state.fireBefore);
		checkPeriod(state.fireAfter);
		var before = mo.spec({ref: ref, period: state.fireBefore.slice(), metric: 'median', quality: state.quality});
		var after = mo.spec({ref: ref, period: state.fireAfter.slice(), metric: 'median', quality: state.quality});
		var scale = Number(e.m);
		var out = mo.burnRatio(before, after, state.region, scale, state.info.crs);
		var name = title(e, ['RBR', before.period.join('/') + ' → ' + after.period.join('/')]);
		var vis = {min: -0.5, max: 0.5, palette: mo.DIVERGING.slice().reverse()};
		map.addLayer(out.image.select('rbr'), vis, name);
		colourBar(vis, name);
		var id = start();
		out.stats.evaluate(guardedAsync(id, function (fc) {
			var rows = mo.rbrTable(fc.features);
			var stats = ['mean', 'median', 'p10', 'p90', 'min', 'max'];
			var table = [[t('region')].concat(stats.map(metricName), [t('hectares')])].concat(rows.map(function (r) {
				return [r.region].concat(stats.map(function (k) { return r[k] === null ? '' : num(r[k], 3); }),
					[num(r.ha, 4)]);
			}));
			show([ui.Label(name, {fontWeight: 'bold'}), ui.Label(t('rbrNote'), SMALL), ui.Chart(table, 'Table'),
				ui.Label(fmt(t('scaleNote'), num(scale)), SMALL), csvWidget(rows, mo.RBR_COLUMNS, name),
				downloadWidget(out.image, e, ['rbr', 'dnbr', 'nbr_before', 'nbr_after'], name)]);
		}));
	}

	function burn() {
		if (state.fireIndex === 'RBR') return burnRatio();
		var ref = state.fireSensor === 'Landsat' ? 101 : 102;
		var e = mo.byRef(ref);
		if (!ready(e)) return;
		checkPeriod(state.fireBefore);
		checkPeriod(state.fireAfter);
		var before = mo.spec({ref: ref, period: state.fireBefore.slice(), metric: 'median', quality: state.quality});
		var after = mo.spec({ref: ref, period: state.fireAfter.slice(), metric: 'median', quality: state.quality});
		var scale = Number(e.m);
		var out = mo.burnSeverity(before, after, state.region, scale, state.info.crs);
		var names = mo.SEVERITY.map(function (c) { return state.lang === 'en' ? c[3] : c[2]; });
		var name = title(e, [t('dnbr'), before.period.join('/') + ' → ' + after.period.join('/')]);
		map.addLayer(out.image.select('severity'), {min: -2, max: 4, palette: mo.SEVERITY_COLOURS}, name);
		classLegend(t('fire'), names, mo.SEVERITY_COLOURS);
		var id = start();
		out.hectares.evaluate(guardedAsync(id, function (fc) {
			var rows = [];
			fc.features.forEach(function (f) {
				rows = rows.concat(mo.severityTable(f.properties.groups, String(f.properties.name), state.lang));
			});
			var burned = rows.filter(function (r) { return r['class'] >= 1; }).reduce(function (a, r) { return a + r.ha; }, 0);
			var regions = regionsOf(rows);
			var table = [[t('klass'), t('dnbr'), t('hectares')]].concat(rows.map(function (r) {
				var range = (r.dnbr_min === null ? '< ' + num(r.dnbr_max) : r.dnbr_max === null ? '≥ ' + num(r.dnbr_min) :
					num(r.dnbr_min) + ' – ' + num(r.dnbr_max));
				return [(regions.length > 1 ? r.region + ': ' : '') + r.label, range, num(r.ha, 4)];
			}));
			show([ui.Label(name, {fontWeight: 'bold'}), ui.Label(fmt(t('burned'), num(burned, 4))),
				ui.Chart(table, 'Table'), ui.Label(fmt(t('scaleNote'), num(scale)), SMALL),
				csvWidget(rows, ['region', 'class', 'label', 'dnbr_min', 'dnbr_max', 'ha'], name),
				downloadWidget(out.image, e, ['dnbr', 'severity', 'nbr_before', 'nbr_after'], name)]);
		}));
	}

	function fireWidgets() {
		var w = [header(t('fire'))];
		w.push(row(ui.Label(t('sensor')), select([{value: 'Sentinel-2', label: 'Sentinel-2 (10 m)'},
			{value: 'Landsat', label: 'Landsat (30 m)'}], state.fireSensor, function (v) { state.fireSensor = v; })));
		w.push(row(ui.Label(t('index')), select(['dNBR', 'RBR'].map(function (i) {
			return {value: i, label: t('idx_' + i)};
		}), state.fireIndex, function (v) { state.fireIndex = v; }, '190px')));
		w.push(ui.Label(t('before'), {margin: '4px 8px 0 8px'}));
		w.push(row(box(state.fireBefore[0], function (v) { state.fireBefore[0] = v.trim(); }), ui.Label(t('to')),
			box(state.fireBefore[1], function (v) { state.fireBefore[1] = v.trim(); })));
		w.push(ui.Label(t('after'), {margin: '4px 8px 0 8px'}));
		w.push(row(box(state.fireAfter[0], function (v) { state.fireAfter[0] = v.trim(); }), ui.Label(t('to')),
			box(state.fireAfter[1], function (v) { state.fireAfter[1] = v.trim(); })));
		w.push(button(t('burn'), guarded(burn)));
		return w;
	}

	// About ---------------------------------------------------------------------------------------------------------

	function aboutWidgets() {
		var a = mo.CATALOG.about;
		var w = [header(t('about'))];
		w.push(ui.Label(a.description[state.lang], SMALL));
		w.push(ui.Label(a.acknowledgements[state.lang], SMALL));
		w.push(ui.Label(t('cite') + ': ' + a.citation, SMALL, 'https://doi.org/' + a.doi));
		w.push(row(ui.Label(t('manual'), {fontSize: '12px'}, a.manual + (state.lang === 'en' ? '/Earth-Engine-app' :
			'/App-de-Earth-Engine')),
			ui.Label(t('repository'), {fontSize: '12px'}, a.repository)));
		a.logos.forEach(function (url) {
			w.push(ui.Label({value: 'MonitorEO', imageUrl: url, style: {margin: '8px'}}));
		});
		return w;
	}

	// The panel of controls, rebuilt from STATE when something changes its options --------------------------------

	function render() {
		controls.clear();
		controls.add(row(ui.Label('MonitorEO', {fontWeight: 'bold', fontSize: '22px', stretch: 'horizontal'}),
			button(t('language'), function () {
				state.lang = state.lang === 'es' ? 'en' : 'es';
				render();
			})));
		controls.add(ui.Label(t('subtitle'), SMALL));
		[regionWidgets(), variableWidgets(), mapWidgets(), seriesWidgets(), trendWidgets(), fireWidgets(),
			aboutWidgets()].forEach(function (ws) {
			ws.forEach(function (w) { controls.add(w); });
		});
	}

	render();
})();
