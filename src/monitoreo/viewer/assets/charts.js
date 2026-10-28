// Charts of the reports, made with Vega-Lite from the CSV of each result: time series (with the Sen lines of their
// trends), trends of each part of the year, comparison of two periods and burn severity, each with its table.
'use strict';

MO.chart = (() => {
	const {el} = MO;
	const NUMERIC = new Set(['value', 'n_pixels', 'n_images', 'n', 'tau', 'z', 'p_value', 'slope', 'intercept', 'first_year',
		'last_year', 'reference', 'other', 'difference', 'n_reference', 'n_other', 'class', 'dnbr_min', 'dnbr_max', 'ha',
		'scale_m']);
	const COLUMNS = {
		region: 'Región', date: 'Fecha', value: 'Valor', n_images: 'Imágenes', n_pixels: 'Píxeles válidos',
		label: 'Parte del año', n: 'Años', tau: 'τ', z: 'Z', p_value: 'p-valor', significant: 'Significativa',
		slope: 'Pendiente', intercept: 'Valor inicial', first_year: 'Primer año', last_year: 'Último año',
		reference: 'Referencia', other: 'Otro periodo', difference: 'Diferencia', n_reference: 'Años (ref.)',
		n_other: 'Años (otro)', class: 'Clase', dnbr_min: 'dNBR desde', dnbr_max: 'dNBR hasta', ha: 'Hectáreas',
	};
	const TABLES = {
		series: ['region', 'date', 'value', 'n_images', 'n_pixels'],
		trends: ['region', 'label', 'slope', 'p_value', 'significant', 'tau', 'z', 'n', 'intercept', 'first_year', 'last_year'],
		comparison: ['region', 'label', 'reference', 'other', 'difference', 'n_reference', 'n_other'],
		burn_severity: ['region', 'label', 'class', 'dnbr_min', 'dnbr_max', 'ha'],
	};
	const LOCALE = {decimal: ',', thousands: '.', grouping: [3], currency: ['', ' €'], minus: '−'};
	const TIME_LOCALE = {
		dateTime: '%A, %e de %B de %Y, %X', date: '%d/%m/%Y', time: '%H:%M:%S', periods: ['AM', 'PM'],
		days: ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'],
		shortDays: ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'],
		months: ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'],
		shortMonths: MO.MONTHS,
	};
	const views = [];
	let narrow = false;  // the chart being drawn is narrow (a phone): shorter labels, one column of legend
	const monthLabel = () => narrow ? 'upper(slice(datum.label, 0, 1))' : 'slice(datum.label, 0, 3)';

	function parse(text) {
		const rows = vega.read(text, {type: 'csv'});
		for (const r of rows) {
			for (const k of Object.keys(r)) {
				if (NUMERIC.has(k)) r[k] = r[k] === '' || r[k] === null ? null : Number(r[k]);
			}
			if ('significant' in r) r.significant = String(r.significant).toLowerCase() === 'true';
		}
		return rows;
	}

	function dark() {
		return getComputedStyle(document.documentElement).colorScheme.includes('dark');
	}

	function config() {
		const c = MO.css;
		return {
			background: null, font: c('--font'), padding: {left: 2, right: 8, top: 6, bottom: 2},
			view: {stroke: null},
			axis: {labelColor: c('--ink-2'), titleColor: c('--ink-2'), gridColor: c('--grid'), domainColor: c('--baseline'),
				tickColor: c('--baseline'), labelFontSize: 12, titleFontSize: 12, titleFontWeight: 'normal', labelFont: c('--font'),
				titleFont: c('--font')},
			axisY: {domain: false, ticks: false, titlePadding: 10},
			axisX: {grid: false},
			legend: {labelColor: c('--ink-2'), titleColor: c('--ink-2'), labelFontSize: 12.5, orient: 'top', title: null,
				labelFont: c('--font'), symbolStrokeWidth: 2.5, labelLimit: 360},
			title: {color: c('--ink'), fontSize: 13, fontWeight: 600, anchor: 'start', font: c('--font')},
			line: {strokeWidth: 2},
			bar: {cornerRadiusEnd: 3},
			text: {color: c('--ink-2'), font: c('--font')},
		};
	}

	function palette() {
		return ['--series-1', '--series-2', '--series-3', '--series-4'].map(MO.css)
			.concat(['#e87ba4', '#008300', '#6250d6', '#e34948']);
	}

	async function embed(box, spec) {
		spec = Object.assign({$schema: 'https://vega.github.io/schema/vega-lite/v6.json', config: config()}, spec);
		const res = await vegaEmbed(box, spec, {
			renderer: 'svg', actions: {export: true, source: false, compiled: false, editor: false},
			formatLocale: LOCALE, timeFormatLocale: TIME_LOCALE, tooltip: {theme: dark() ? 'dark' : 'light'},
			i18n: {PNG_ACTION: 'Guardar como PNG', SVG_ACTION: 'Guardar como SVG', CLICK_TO_VIEW_ACTIONS: 'Opciones del gráfico'},
		});
		return res;
	}

	const utc = (d) => {
		const [y, m, day] = String(d).slice(0, 10).split('-').map(Number);
		return Date.UTC(y, m - 1, day || 1);
	};
	const regionsOf = (rows) => [...new Set(rows.map((r) => r.region))];

	// Time series, with the Sen lines of the trends of the report over it (annual series) and, if it is long, an
	// overview to choose the years shown.
	function seriesSpec(rows, result) {
		const regions = regionsOf(rows);
		const annual = result.step === 'annual';
		const label = (r) => regions.length > 1 ? r : (annual ? 'Media de cada año' : 'Media de cada mes');
		const data = rows.map((r) => ({...r, t: utc(r.date), serie: label(r.region)}));
		const md = String(rows[0]?.date || '2000-01-01').slice(4, 10);
		const sen = (result.sen || []).flatMap((s) => [s.from, s.to].map((y) => ({
			t: utc(`${y}${md}`), value: s.intercept + s.slope * (y - s.origin), region: s.region,
			serie: `Recta de Sen ${s.period}` + (regions.length > 1 ? ` · ${s.region}` : '') +
				(s.significant ? ` (p ${MO.pValue(s.p_value).startsWith('<') ? '' : '= '}${MO.pValue(s.p_value)})` : ' (no significativa)'),
			slope: s.slope, p_value: s.p_value})));
		const domain = [...new Set(data.map((d) => d.serie).concat(sen.map((d) => d.serie)))];
		const color = {field: 'serie', type: 'nominal', scale: {domain, range: palette()},
			legend: domain.length > 1 ? {columns: narrow ? 1 : Math.min(domain.length, 2)} : null};
		const yTitle = result.unit || result.call?.args?.variable || null;
		const x = (brush) => ({field: 't', type: 'temporal', title: null, scale: Object.assign({type: 'utc'},
			brush ? {domain: {param: 'brush', encoding: 'x'}} : {}), axis: Object.assign({labelOverlap: true}, annual ? {format: '%Y'} : {})});
		const y = {field: 'value', type: 'quantitative', title: yTitle, scale: {zero: false}};
		const long = !annual && rows.length > 60;
		const tipTime = {field: 't', type: 'temporal', timeUnit: annual ? 'utcyear' : 'utcyearmonth', title: annual ? 'Año' : 'Mes',
			format: annual ? '%Y' : '%B de %Y'};
		const tooltip = regions.length > 1
			? [tipTime, ...regions.map((r) => ({field: r, type: 'quantitative', title: r, format: '.4~g'}))]
			: [tipTime, {field: 'value', type: 'quantitative', title: 'Valor', format: '.4~g'},
				{field: 'n_images', type: 'quantitative', title: 'Imágenes'}, {field: 'n_pixels', type: 'quantitative', title: 'Píxeles válidos', format: ',d'}];
		const layers = [
			{mark: {type: 'line', interpolate: 'linear', invalid: 'break-paths-show-domains'}, encoding: {x: x(long), y, color}},
			annual && {mark: {type: 'point', filled: true, size: 40, opacity: 1}, encoding: {x: x(long), y, color}},
			sen.length && {data: {values: sen}, mark: {type: 'line', strokeDash: [6, 4], strokeWidth: 2},
				encoding: {x: x(long), y, color, detail: {field: 'serie'},
					tooltip: [{field: 'serie', title: 'Recta'}, {field: 'slope', title: 'Pendiente por año', format: '+.3~g'}]}},
			{transform: regions.length > 1 ? [{pivot: 'region', value: 'value', groupby: ['t']}] : [],
				mark: {type: 'rule', color: MO.css('--ink-2'), strokeWidth: 1},
				params: [{name: 'hover', select: {type: 'point', encodings: ['x'], nearest: true, on: 'pointerover', clear: 'pointerout'}}],
				encoding: {x: x(long), opacity: {condition: {param: 'hover', empty: false, value: 0.5}, value: 0}, tooltip}},
			{mark: {type: 'point', filled: true, size: 70},
				encoding: {x: x(long), y, color, opacity: {condition: {param: 'hover', empty: false, value: 1}, value: 0}}},
		].filter(Boolean);
		const detail = {height: 280, width: 'container', layer: layers};
		if (!long) return Object.assign({data: {values: data}}, detail);
		return {data: {values: data}, vconcat: [detail, {
			height: 46, width: 'container',
			mark: {type: 'line', strokeWidth: 1, invalid: 'break-paths-show-domains'},
			params: [{name: 'brush', select: {type: 'interval', encodings: ['x']}}],
			encoding: {x: {field: 't', type: 'temporal', title: 'Arrastre aquí para elegir los años', scale: {type: 'utc'},
				axis: {format: '%Y', labelOverlap: true, titleFontSize: 11, titleColor: MO.css('--muted')}},
			y: {field: 'value', type: 'quantitative', title: null, axis: {labels: false, grid: false}, scale: {zero: false}},
			color: Object.assign({}, color, {legend: null})},
		}], spacing: 6};
	}

	// Trends of each part of the year (Sen slope, coloured where significant).
	function trendsSpec(rows, result) {
		const alpha = result.alpha || 0.05;
		const yes = `Significativa (p < ${MO.num(alpha)})`, no = 'No significativa';
		const order = [...new Map(rows.map((r) => [r.key, r.label])).values()];
		const data = rows.map((r) => ({...r, sig: r.significant ? yes : no, decade: r.slope === null ? null : r.slope * 10}));
		const monthly = result.step === 'monthly';
		return {
			data: {values: data}, height: 260, width: 'container',
			layer: [
				{mark: {type: 'bar', width: {band: 0.7}},
					encoding: {
						x: {field: 'label', type: 'ordinal', sort: order, title: null,
							axis: {labelAngle: 0, labelExpr: monthly ? monthLabel() : 'datum.label'}},
						y: {field: 'slope', type: 'quantitative', title: `Pendiente de Sen (${result.slope_unit || 'por año'})`},
						color: {field: 'sig', type: 'nominal', scale: {domain: [yes, no], range: [MO.css('--series-1'), MO.css('--not-significant')]},
							legend: {columns: narrow ? 1 : 2}},
						tooltip: [{field: 'label', title: monthly ? 'Mes' : 'Parte del año'},
							{field: 'slope', title: 'Pendiente por año', format: '+.3~g'},
							{field: 'decade', title: 'Pendiente por década', format: '+.3~g'},
							{field: 'p_value', title: 'p-valor', format: '.2~g'}, {field: 'tau', title: 'τ de Kendall', format: '.2f'},
							{field: 'n', title: 'Años con datos'}]}},
				{mark: {type: 'rule', color: MO.css('--baseline')}, encoding: {y: {datum: 0}}},
			],
		};
	}

	// Trend of the year (one part): the numbers, without a chart.
	function trendTiles(rows, result) {
		const unit = result.slope_unit || 'por año';
		return rows.map((r) => el('div', {},
			rows.length > 1 && el('p', {class: 'region-name'}, r.region),
			el('div', {class: 'stats'},
				el('div', {class: 'stat'}, el('div', {class: 'label'}, `Pendiente de Sen (${unit})`),
					el('div', {class: 'value'}, MO.signed(r.slope, 3)),
					el('div', {class: 'sub'}, `${MO.signed(r.slope * 10, 3)} por década`)),
				el('div', {class: 'stat'}, el('div', {class: 'label'}, 'p-valor de Mann-Kendall'),
					el('div', {class: 'value'}, MO.pValue(r.p_value)),
					el('div', {class: 'sub'}, el('span', {class: `badge ${r.significant ? 'yes' : 'no'}`},
						r.significant ? `Significativa (p < ${MO.num(result.alpha || 0.05)})` : 'No significativa'))),
				el('div', {class: 'stat'}, el('div', {class: 'label'}, 'τ de Kendall'), el('div', {class: 'value'}, MO.num(r.tau, 2))),
				el('div', {class: 'stat'}, el('div', {class: 'label'}, 'Años con datos'), el('div', {class: 'value'}, MO.num(r.n)),
					el('div', {class: 'sub'}, `${r.first_year}-${r.last_year}`)))));
	}

	// Comparison of two periods: the value of each part of the year in both, and their difference.
	function comparisonSpec(rows, result) {
		const [a, b] = result.names || ['Referencia', 'Otro periodo'];
		const order = [...new Map(rows.map((r) => [r.key, r.label])).values()];
		const monthly = result.step === 'monthly';
		const long = rows.flatMap((r) => [
			{label: r.label, periodo: a, value: r.reference, years: r.n_reference, difference: r.difference},
			{label: r.label, periodo: b, value: r.other, years: r.n_other, difference: r.difference}]);
		const x = {field: 'label', type: 'ordinal', sort: order, title: null,
			axis: {labelAngle: 0, labelExpr: monthly ? monthLabel() : 'datum.label'}};
		const color = {field: 'periodo', type: 'nominal', scale: {domain: [a, b], range: [MO.css('--series-1'), MO.css('--series-other')]}};
		const tooltip = [{field: 'label', title: monthly ? 'Mes' : 'Parte del año'}, {field: 'periodo', title: 'Periodo'},
			{field: 'value', title: 'Valor', format: '.4~g'}, {field: 'years', title: 'Años con datos'},
			{field: 'difference', title: `Diferencia (${b} − ${a})`, format: '+.3~g'}];
		return {
			vconcat: [
				{data: {values: long}, height: 240, width: 'container', layer: [
					{mark: {type: 'line', invalid: 'break-paths-show-domains'}, encoding: {x, y: {field: 'value', type: 'quantitative', title: result.unit || result.call?.args?.variable || null}, color}},
					{mark: {type: 'point', filled: true, size: 55, opacity: 1}, encoding: {x, y: {field: 'value', type: 'quantitative'}, color, tooltip}},
				]},
				{data: {values: rows}, height: 120, width: 'container',
					title: {text: `Diferencia: ${b} menos ${a}`, fontSize: 12.5, fontWeight: 'normal', color: MO.css('--ink-2')},
					layer: [
						{mark: {type: 'bar', width: {band: 0.6}, color: MO.css('--ink-2')},
							encoding: {x, y: {field: 'difference', type: 'quantitative', title: result.unit || result.call?.args?.variable || null},
								tooltip: [{field: 'label', title: monthly ? 'Mes' : 'Parte del año'},
									{field: 'difference', title: 'Diferencia', format: '+.3~g'}]}},
						{mark: {type: 'rule', color: MO.css('--baseline')}, encoding: {y: {datum: 0}}},
					]},
			],
			spacing: 18,
		};
	}

	// Burn severity: hectares of each class (without the unburned one, much bigger), and the burned area.
	function burnSpec(rows, result) {
		const classes = result.classes || [];
		const data = rows.filter((r) => r.class !== 0);
		return {
			data: {values: data}, width: 'container', height: {step: 30},
			layer: [
				{mark: {type: 'bar', height: {band: 0.7}},
					encoding: {
						y: {field: 'label', type: 'nominal', sort: classes.map((c) => c.label), title: null},
						x: {field: 'ha', type: 'quantitative', title: 'Hectáreas'},
						color: {field: 'label', type: 'nominal', legend: null,
							scale: {domain: classes.map((c) => c.label), range: classes.map((c) => c.color)}},
						tooltip: [{field: 'label', title: 'Clase'}, {field: 'ha', title: 'Hectáreas', format: ',.1f'},
							{field: 'dnbr_min', title: 'dNBR desde', format: '.2f'}, {field: 'dnbr_max', title: 'dNBR hasta', format: '.2f'}]}},
				{mark: {type: 'text', align: 'left', dx: 5, fontSize: 12.5},
					transform: [{calculate: "datum.ha < 10 ? format(datum.ha, ',.1f') : format(datum.ha, ',.0f')", as: 'text'}],
					encoding: {y: {field: 'label', type: 'nominal', sort: classes.map((c) => c.label)}, x: {field: 'ha', type: 'quantitative'},
						text: {field: 'text', type: 'nominal'}}},
			],
		};
	}

	function burnTiles(rows) {
		const sum = (f) => rows.filter(f).reduce((s, r) => s + (r.ha || 0), 0);
		return el('div', {class: 'stats'},
			el('div', {class: 'stat'}, el('div', {class: 'label'}, 'Superficie quemada (dNBR ≥ 0,1)'),
				el('div', {class: 'value'}, `${MO.round(sum((r) => r.class >= 1))} ha`)),
			el('div', {class: 'stat'}, el('div', {class: 'label'}, 'Severidad moderada o alta'),
				el('div', {class: 'value'}, `${MO.round(sum((r) => r.class >= 2))} ha`)),
			el('div', {class: 'stat'}, el('div', {class: 'label'}, 'Sin quemar'),
				el('div', {class: 'value'}, `${MO.round(sum((r) => r.class === 0))} ha`)),
			el('div', {class: 'stat'}, el('div', {class: 'label'}, 'Rebrote (dNBR < −0,1)'),
				el('div', {class: 'value'}, `${MO.round(sum((r) => r.class < 0))} ha`)));
	}

	function table(rows, kind) {
		const cols = (TABLES[kind] || Object.keys(rows[0] || {})).filter((c) => rows.length && c in rows[0]);
		const cell = (c, v) => c === 'significant' ? (v ? 'sí' : 'no') : c === 'p_value' ? MO.pValue(v) :
			typeof v === 'number' ? (['n', 'n_images', 'n_pixels', 'first_year', 'last_year', 'class', 'n_reference', 'n_other'].includes(c) ? String(v) : MO.num(v)) : (v ?? '–');
		return el('div', {class: 'table-wrap'}, el('table', {class: 'data'},
			el('thead', {}, el('tr', {}, cols.map((c) => el('th', {scope: 'col'}, COLUMNS[c] || c)))),
			el('tbody', {}, rows.map((r) => el('tr', {}, cols.map((c) => el('td', {}, cell(c, r[c]))))))));
	}

	// Draw the chart of RESULT (its CSV is BASE + result.csv) in CONTAINER; returns its rows.
	async function render(container, result, base) {
		const rows = parse(await MO.text(base + result.csv));
		const kind = result.chart;
		const regions = regionsOf(rows);
		const box = el('div', {class: 'chart'});
		const draw = async (subset) => {
			box.replaceChildren();
			narrow = (box.clientWidth || container.clientWidth) < 520;
			const parts = new Set(subset.map((r) => r.key)).size;
			if (kind === 'series') return embed(box, seriesSpec(subset, result));
			if (kind === 'trends' && parts > 1) return embed(box, trendsSpec(subset, result));
			if (kind === 'trends') return box.append(...trendTiles(subset, result));
			if (kind === 'comparison') return embed(box, comparisonSpec(subset, result));
			if (kind === 'burn_severity') {
				box.append(burnTiles(subset));
				const inner = el('div');
				box.append(inner);
				return embed(inner, burnSpec(subset, result));
			}
			return box.append(table(subset, kind));
		};
		let current = rows;
		if (regions.length > 1 && ['comparison', 'burn_severity'].includes(kind) ||
			regions.length > 1 && kind === 'trends' && new Set(rows.map((r) => r.key)).size > 1) {
			const id = `c-${result.id}-region`;
			current = rows.filter((r) => r.region === regions[0]);
			container.append(el('div', {class: 'map-controls'}, el('div', {class: 'field grow'},
				el('label', {for: id}, 'Región'),
				el('select', {id, onchange: (e) => { current = rows.filter((r) => r.region === e.target.value); draw(current); }},
					regions.map((r) => el('option', {value: r}, r))))));
		}
		container.append(box);
		await draw(current);
		views.push(() => draw(current));
		return {rows, table: () => table(rows, kind)};
	}

	// draw the charts again with the colours of the theme when it changes
	window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => views.forEach((f) => f()));

	return {render, parse, table};
})();
