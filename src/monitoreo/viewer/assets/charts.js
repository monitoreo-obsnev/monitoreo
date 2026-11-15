// Charts of the reports, made with Vega-Lite from the CSV of each result: time series (with the Sen lines of their
// trends, or a line per year over the days of the year), the seasonal profile of one or two variables by day of the
// year (on two y axes), trends of each part of the year, comparison of two periods and burn severity (the area of each
// class), each with its table; or only a table (the statistics of the RBR of each region).
'use strict';

MO.chart = (() => {
	const {el} = MO;
	const NUMERIC = new Set(['value', 'n_pixels', 'n_images', 'n', 'tau', 'z', 'p_value', 'slope', 'intercept', 'first_year',
		'last_year', 'reference', 'other', 'difference', 'n_reference', 'n_other', 'class', 'dnbr_min', 'dnbr_max',
		'rdnbr_min', 'rdnbr_max', 'ha', 'scale_m', 'mean', 'median', 'std', 'cv', 'p10', 'p90', 'min', 'max', 'percent',
		'value_from', 'value_to', 'year', 'zone', 'zone_from', 'zone_to', 'p25', 'p50', 'p75', 'p5', 'p95', 'distance_m',
		'lon', 'lat', 'elevation', 'n_pixels', 'doy', 'n_years', 'mode', 'group', 'count']);
	const COLUMNS = {
		region: 'Region', date: 'Date', value: 'Value', n_images: 'Images', n_pixels: 'Valid pixels',
		label: 'Part of the year', n: 'Years', tau: 'τ', z: 'Z', p_value: 'p-value', significant: 'Significant',
		slope: 'Slope', intercept: 'Initial value', first_year: 'First year', last_year: 'Last year',
		reference: 'Reference', other: 'Other period', difference: 'Difference', n_reference: 'Years (ref.)',
		n_other: 'Years (other)', class: 'Class', dnbr_min: 'dNBR from', dnbr_max: 'dNBR to', rdnbr_min: 'RdNBR from',
		rdnbr_max: 'RdNBR to', ha: 'Hectares', mean: 'Mean', median: 'Median', std: 'Standard deviation',
		cv: 'Coefficient of variation (%)', p10: 'Percentile 10',
		p90: 'Percentile 90', min: 'Minimum', max: 'Maximum', percent: '% of the area with classes',
		landcover: 'Land cover', value_from: 'From', value_to: 'To', map: 'Map', year: 'Year',
		from_label: 'From (first year)', to_label: 'To (other year)', other_year: 'Other year',
		zone_label: 'Zone', p25: 'Percentile 25', p50: 'Median (percentile 50)', p75: 'Percentile 75',
		p5: 'Percentile 5', p95: 'Percentile 95', distance_m: 'Distance (m)', lon: 'Longitude', lat: 'Latitude',
		elevation: 'Elevation (m)', variable: 'Variable', part: 'Step of the year', doy: 'Day of the year',
		n_years: 'Years', mode: 'Majority class', mode_label: 'Majority class (name)', group: 'Biome (code)',
		group_label: 'Biome', count: 'Pixels',
	};
	const TABLES = {
		series: ['region', 'date', 'value', 'n_images', 'n_pixels'],
		trends: ['region', 'label', 'slope', 'p_value', 'significant', 'tau', 'z', 'n', 'intercept', 'first_year', 'last_year'],
		comparison: ['region', 'label', 'reference', 'other', 'difference', 'n_reference', 'n_other'],
		burn_severity: ['region', 'label', 'class', 'dnbr_min', 'dnbr_max', 'rdnbr_min', 'rdnbr_max', 'ha'],
		areas: ['region', 'label', 'group_label', 'landcover', 'value_from', 'value_to', 'ha', 'percent'],
		transitions: ['region', 'from_label', 'to_label', 'ha', 'percent'],
		transect: ['distance_m', 'value', 'elevation', 'lon', 'lat'],
		doy: ['region', 'date', 'value', 'n_images', 'n_pixels'],
		doy_profile: ['region', 'variable', 'label', 'doy', 'value', 'n_years'],
	};
	// the titles of the columns of a table that are not those of COLUMNS
	const HEADS = {doy_profile: {label: 'Step of the year'}};
	// the statistics of the RBR of each region (burn_severity with the index RBR, without classes): a table, with the
	// standard deviation and the coefficient of variation (RBR_BASE: those of the reports published before them)
	const RBR_STATS = ['region', 'mean', 'median', 'std', 'cv', 'p10', 'p90', 'min', 'max', 'ha'];
	const RBR_BASE = ['region', 'mean', 'median', 'p10', 'p90', 'min', 'max', 'ha'];
	const LOCALE = {decimal: '.', thousands: ',', grouping: [3], currency: ['$', ''], minus: '−'};
	const TIME_LOCALE = {
		dateTime: '%A, %e %B %Y, %X', date: '%d/%m/%Y', time: '%H:%M:%S', periods: ['AM', 'PM'],
		days: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
		shortDays: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
		months: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
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
			i18n: {PNG_ACTION: 'Save as PNG', SVG_ACTION: 'Save as SVG', CLICK_TO_VIEW_ACTIONS: 'Options of the chart'},
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
		const label = (r) => regions.length > 1 ? r : (annual ? 'Mean of each year' : 'Mean of each month');
		const data = rows.map((r) => ({...r, t: utc(r.date), serie: label(r.region)}));
		const md = String(rows[0]?.date || '2000-01-01').slice(4, 10);
		const sen = (result.sen || []).flatMap((s) => [s.from, s.to].map((y) => ({
			t: utc(`${y}${md}`), value: s.intercept + s.slope * (y - s.origin), region: s.region,
			serie: `Sen line ${s.period}` + (regions.length > 1 ? ` · ${s.region}` : '') +
				(s.significant ? ` (p ${MO.pValue(s.p_value).startsWith('<') ? '' : '= '}${MO.pValue(s.p_value)})` : ' (not significant)'),
			slope: s.slope, p_value: s.p_value})));
		const domain = [...new Set(data.map((d) => d.serie).concat(sen.map((d) => d.serie)))];
		const color = {field: 'serie', type: 'nominal', scale: {domain, range: palette()},
			legend: domain.length > 1 ? {columns: narrow ? 1 : Math.min(domain.length, 2)} : null};
		const yTitle = result.ylabel || result.unit || result.call?.args?.variable || null;
		const x = (brush) => ({field: 't', type: 'temporal', title: null, scale: Object.assign({type: 'utc'},
			brush ? {domain: {param: 'brush', encoding: 'x'}} : {}), axis: Object.assign({labelOverlap: true}, annual ? {format: '%Y'} : {})});
		const y = {field: 'value', type: 'quantitative', title: yTitle, scale: {zero: false}};
		const long = !annual && rows.length > 60;
		const tipTime = {field: 't', type: 'temporal', timeUnit: annual ? 'utcyear' : 'utcyearmonth', title: annual ? 'Year' : 'Month',
			format: annual ? '%Y' : '%B %Y'};
		const tooltip = regions.length > 1
			? [tipTime, ...regions.map((r) => ({field: r, type: 'quantitative', title: r, format: '.4~g'}))]
			: [tipTime, {field: 'value', type: 'quantitative', title: 'Value', format: '.4~g'},
				{field: 'n_images', type: 'quantitative', title: 'Images'}, {field: 'n_pixels', type: 'quantitative', title: 'Valid pixels', format: ',d'}];
		const layers = [
			{mark: {type: 'line', interpolate: 'linear', invalid: 'break-paths-show-domains'}, encoding: {x: x(long), y, color}},
			annual && {mark: {type: 'point', filled: true, size: 40, opacity: 1}, encoding: {x: x(long), y, color}},
			sen.length && {data: {values: sen}, mark: {type: 'line', strokeDash: [6, 4], strokeWidth: 2},
				encoding: {x: x(long), y, color, detail: {field: 'serie'},
					tooltip: [{field: 'serie', title: 'Line'}, {field: 'slope', title: 'Slope per year', format: '+.3~g'}]}},
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
			encoding: {x: {field: 't', type: 'temporal', title: 'Drag here to choose the years', scale: {type: 'utc'},
				axis: {format: '%Y', labelOverlap: true, titleFontSize: 11, titleColor: MO.css('--muted')}},
			y: {field: 'value', type: 'quantitative', title: null, axis: {labels: false, grid: false}, scale: {zero: false}},
			color: Object.assign({}, color, {legend: null})},
		}], spacing: 6};
	}

	// Trends of each part of the year (Sen slope, coloured where significant).
	function trendsSpec(rows, result) {
		const alpha = result.alpha || 0.05;
		const yes = `Significant (p < ${MO.num(alpha)})`, no = 'Not significant';
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
						y: {field: 'slope', type: 'quantitative', title: `Sen's slope (${result.slope_unit || 'per year'})`},
						color: {field: 'sig', type: 'nominal', scale: {domain: [yes, no], range: [MO.css('--series-1'), MO.css('--not-significant')]},
							legend: {columns: narrow ? 1 : 2}},
						tooltip: [{field: 'label', title: monthly ? 'Month' : 'Part of the year'},
							{field: 'slope', title: 'Slope per year', format: '+.3~g'},
							{field: 'decade', title: 'Slope per decade', format: '+.3~g'},
							{field: 'p_value', title: 'p-value', format: '.2~g'}, {field: 'tau', title: "Kendall's τ", format: '.2f'},
							{field: 'n', title: 'Years with data'}]}},
				{mark: {type: 'rule', color: MO.css('--baseline')}, encoding: {y: {datum: 0}}},
			],
		};
	}

	// Trend of the year (one part): the numbers, without a chart.
	function trendTiles(rows, result) {
		const unit = result.slope_unit || 'per year';
		return rows.map((r) => el('div', {},
			rows.length > 1 && el('p', {class: 'region-name'}, r.region),
			el('div', {class: 'stats'},
				el('div', {class: 'stat'}, el('div', {class: 'label'}, `Sen's slope (${unit})`),
					el('div', {class: 'value'}, MO.signed(r.slope, 3)),
					el('div', {class: 'sub'}, `${MO.signed(r.slope * 10, 3)} per decade`)),
				el('div', {class: 'stat'}, el('div', {class: 'label'}, 'Mann-Kendall p-value'),
					el('div', {class: 'value'}, MO.pValue(r.p_value)),
					el('div', {class: 'sub'}, el('span', {class: `badge ${r.significant ? 'yes' : 'no'}`},
						r.significant ? `Significant (p < ${MO.num(result.alpha || 0.05)})` : 'Not significant'))),
				el('div', {class: 'stat'}, el('div', {class: 'label'}, "Kendall's τ"), el('div', {class: 'value'}, MO.num(r.tau, 2))),
				el('div', {class: 'stat'}, el('div', {class: 'label'}, 'Years with data'), el('div', {class: 'value'}, MO.num(r.n)),
					el('div', {class: 'sub'}, `${r.first_year}-${r.last_year}`)))));
	}

	// Comparison of two periods: the value of each part of the year in both, and their difference.
	function comparisonSpec(rows, result) {
		const [a, b] = result.names || ['Reference period', 'Other period'];
		const order = [...new Map(rows.map((r) => [r.key, r.label])).values()];
		const monthly = result.step === 'monthly';
		const long = rows.flatMap((r) => [
			{label: r.label, period: a, value: r.reference, years: r.n_reference, difference: r.difference},
			{label: r.label, period: b, value: r.other, years: r.n_other, difference: r.difference}]);
		const x = {field: 'label', type: 'ordinal', sort: order, title: null,
			axis: {labelAngle: 0, labelExpr: monthly ? monthLabel() : 'datum.label'}};
		const color = {field: 'period', type: 'nominal', scale: {domain: [a, b], range: [MO.css('--series-1'), MO.css('--series-other')]}};
		const tooltip = [{field: 'label', title: monthly ? 'Month' : 'Part of the year'}, {field: 'period', title: 'Period'},
			{field: 'value', title: 'Value', format: '.4~g'}, {field: 'years', title: 'Years with data'},
			{field: 'difference', title: `Difference (${b} − ${a})`, format: '+.3~g'}];
		return {
			vconcat: [
				{data: {values: long}, height: 240, width: 'container', layer: [
					{mark: {type: 'line', invalid: 'break-paths-show-domains'}, encoding: {x, y: {field: 'value', type: 'quantitative', title: result.ylabel || result.unit || result.call?.args?.variable || null}, color}},
					{mark: {type: 'point', filled: true, size: 55, opacity: 1}, encoding: {x, y: {field: 'value', type: 'quantitative'}, color, tooltip}},
				]},
				{data: {values: rows}, height: 120, width: 'container',
					title: {text: `Difference: ${b} minus ${a}`, fontSize: 12.5, fontWeight: 'normal', color: MO.css('--ink-2')},
					layer: [
						{mark: {type: 'bar', width: {band: 0.6}, color: MO.css('--ink-2')},
							encoding: {x, y: {field: 'difference', type: 'quantitative', title: result.unit || result.call?.args?.variable || null},
								tooltip: [{field: 'label', title: monthly ? 'Month' : 'Part of the year'},
									{field: 'difference', title: 'Difference', format: '+.3~g'}]}},
						{mark: {type: 'rule', color: MO.css('--baseline')}, encoding: {y: {datum: 0}}},
					]},
			],
			spacing: 18,
		};
	}

	// The burn index of a result of burn severity with classes: 'RdNBR' (Miller & Thode 2007: its CSV has rdnbr_min) or
	// 'dNBR' (the classes of the USGS)
	const burnIndex = (rows, result) => result.index === 'RdNBR' || rows.some((r) => 'rdnbr_min' in r) ? 'RdNBR' : 'dNBR';

	// Burn severity: hectares of each class (without the unburned or unchanged one, much bigger), and the burned area.
	// The names of the classes are those of the legend of the result (its CSV may have been written in another
	// language).
	function burnSpec(rows, result) {
		const classes = result.classes || [];
		const index = burnIndex(rows, result);
		const key = index.toLowerCase();
		const names = new Map(classes.map((c) => [c.value, c.label]));
		const data = rows.filter((r) => r.class !== 0).map((r) => ({...r, label: names.get(r.class) ?? r.label}));
		return {
			data: {values: data}, width: 'container', height: {step: 30},
			layer: [
				{mark: {type: 'bar', height: {band: 0.7}},
					encoding: {
						y: {field: 'label', type: 'nominal', sort: classes.map((c) => c.label), title: null},
						x: {field: 'ha', type: 'quantitative', title: 'Hectares'},
						color: {field: 'label', type: 'nominal', legend: null,
							scale: {domain: classes.map((c) => c.label), range: classes.map((c) => c.color)}},
						tooltip: [{field: 'label', title: 'Class'}, {field: 'ha', title: 'Hectares', format: ',.1f'},
							{field: `${key}_min`, title: `${index} from`, format: index === 'RdNBR' ? '.3f' : '.2f'},
							{field: `${key}_max`, title: `${index} to`, format: index === 'RdNBR' ? '.3f' : '.2f'}]}},
				{mark: {type: 'text', align: 'left', dx: 5, fontSize: 12.5},
					transform: [{calculate: "datum.ha < 10 ? format(datum.ha, ',.1f') : format(datum.ha, ',.0f')", as: 'text'}],
					encoding: {y: {field: 'label', type: 'nominal', sort: classes.map((c) => c.label)}, x: {field: 'ha', type: 'quantitative'},
						text: {field: 'text', type: 'nominal'}}},
			],
		};
	}

	// The hectares of each class of a land cover map, of the classes of a variable or of a trend (area_by_class), with
	// the colours of its chart of Python
	function areasSpec(rows, result) {
		const classes = result.classes || [];
		const labels = classes.map((c) => c.label);
		const data = rows.filter((r) => r.ha > 0);
		return {
			data: {values: data}, width: 'container', height: {step: 24},
			layer: [
				{mark: {type: 'bar', height: {band: 0.7}},
					encoding: {
						y: {field: 'label', type: 'nominal', sort: labels, title: null},
						x: {field: 'ha', type: 'quantitative', title: 'Hectares'},
						color: {field: 'label', type: 'nominal', legend: null,
							scale: {domain: labels, range: classes.map((c) => `#${c.colour || '6baed6'}`)}},
						tooltip: [{field: 'label', title: 'Class'}, {field: 'ha', title: 'Hectares', format: ',.1f'},
							{field: 'percent', title: '% of the area with classes', format: '.1f'}]}},
				{mark: {type: 'text', align: 'left', dx: 5, fontSize: 12},
					transform: [{calculate: "format(datum.percent, '.1f') + ' %'", as: 'text'}],
					encoding: {y: {field: 'label', type: 'nominal', sort: labels}, x: {field: 'ha', type: 'quantitative'},
						text: {field: 'text', type: 'nominal'}}},
			],
		};
	}

	// The range [min, max] of a y axis of a result (ylim, other_ylim), or null (from the data)
	const range = (lim) => Array.isArray(lim) && lim.length === 2 && lim.every(Number.isFinite) && lim[0] < lim[1] ?
		lim : null;
	const yScale = (lim) => lim ? {domain: lim, nice: false, zero: false} : {zero: false};

	// A time series with a line per year over the days of the year (time_series with doy), from the oldest year (light)
	// to the newest (dark, thicker); its y axis, that of the result (ylim) if one was given
	function doySpec(rows, result) {
		const data = rows.map((r) => {
			const d = new Date(`${r.date}T00:00:00Z`);
			const doy = Math.round((d - Date.UTC(d.getUTCFullYear(), 0, 1)) / 864e5) + 1;
			return {...r, year: String(d.getUTCFullYear()), doy, day: new Date(Date.UTC(2000, 0, doy))};
		});
		const newest = data.reduce((y, r) => r.year > y ? r.year : y, '');
		const lim = range(result.ylim);
		return {
			data: {values: data}, width: 'container', height: 260,
			mark: {type: 'line', point: {size: 18}, clip: Boolean(lim)},
			encoding: {
				x: {field: 'day', type: 'temporal', title: null, axis: {format: '%b', tickCount: 12}},
				y: {field: 'value', type: 'quantitative', title: result.ylabel || result.unit || 'Value', scale: yScale(lim)},
				color: {field: 'year', type: 'ordinal', title: 'Year', scale: {scheme: 'viridis', reverse: true}},
				strokeWidth: {condition: {test: {field: 'year', equal: newest}, value: 2.5}, value: 1.2},
				tooltip: [{field: 'date', title: 'Date'}, {field: 'value', title: 'Value', format: '.4~g'}],
			},
		};
	}

	// The day of the year of the first day of each month (that of a year of 365 days, as charts.MONTH_STARTS of Python)
	const MONTH_STARTS = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];
	// the colours of the line of the left axis and of the right axis of a profile (those of charts.doy_profile_png of
	// Python if the theme has none)
	const PROFILE_COLOURS = [['--series-1', '#1f77b4'], ['--series-other', '#d62728']];
	// the metric between the years of a profile, as the texts say it
	const BETWEEN = {mean: 'mean', median: 'median', min: 'minimum', max: 'maximum', std: 'standard deviation',
		cv: 'coefficient of variation'};
	const betweenText = (m) => BETWEEN[m] || (/^p\d/.test(m) ? `percentile ${m.slice(1)}` : m);

	// The seasonal profile by day of the year of one or two variables (time_series with doy and interannual or
	// other_variable): for each step of the year (each month, 16-day period or calendar day), the metric between the
	// years of its values, at its day of the year, a line per variable (result.variables, as the column variable of its
	// CSV names them). The first one on the left axis and the other one on the right axis, each with its own scale (the
	// range of the result, ylim and other_ylim, if given; else from the minimum to the maximum of its variable) and,
	// with two, its title and labels in the colour of its line; a line at 0 where it is inside an axis (that of the
	// right axis, dotted, only if its range is not that of the left one), as charts.doy_profile_png of Python.
	function doyProfileSpec(rows, result) {
		const names = (result.variables || []).length ? result.variables.slice(0, 2) :
			[...new Set(rows.map((r) => r.variable))].slice(0, 2);
		const labels = names.map((n, i) => (result.labels || [])[i] || n);
		const two = names.length > 1;
		const colours = PROFILE_COLOURS.map(([v, c]) => MO.css(v) || c);
		const lims = [range(result.ylim), two ? range(result.other_ylim) : null];
		const titles = [result.ylabel || labels[0], result.other_ylabel || labels[1]];
		const data = rows.filter((r) => r.doy !== null && names.includes(r.variable))
			.map((r) => ({...r, serie: labels[names.indexOf(r.variable)]}));
		const months = JSON.stringify(MO.MONTHS), starts = JSON.stringify(MONTH_STARTS);
		const month = `${months}[indexof(${starts}, datum.value)]`;
		const x = {field: 'doy', type: 'quantitative', title: null, scale: {domain: [1, 366], nice: false, zero: false},
			axis: {values: MONTH_STARTS, grid: false, labelExpr: narrow ? `slice(${month}, 0, 1)` : month}};
		const color = {field: 'serie', type: 'nominal', scale: {domain: labels, range: colours.slice(0, labels.length)},
			legend: two ? {columns: narrow ? 1 : 2} : null};
		const tooltip = [{field: 'label', title: 'Step of the year'}, {field: 'serie', title: 'Variable'},
			{field: 'value', title: `Value (${betweenText(result.interannual || 'median')} of the years)`, format: '.4~g'},
			{field: 'n_years', title: 'Years with a value'}, {field: 'doy', title: 'Day of the year'}];
		const axis = (k) => {
			const lim = lims[k], c = colours[k];
			const only = {filter: {field: 'variable', equal: names[k]}};
			const values = data.filter((d) => d.variable === names[k] && Number.isFinite(d.value)).map((d) => d.value);
			const [lo, hi] = lim || (values.length ? [Math.min(...values), Math.max(...values)] : [0, 0]);
			const y = (more) => Object.assign({type: 'quantitative', title: titles[k], scale: yScale(lim),
				axis: Object.assign({orient: k ? 'right' : 'left', grid: !k}, two ? {titleColor: c, labelColor: c} : {})}, more);
			const layer = [
				{transform: [only], mark: {type: 'line', clip: Boolean(lim), invalid: 'break-paths-show-domains'},
					encoding: {x, y: y({field: 'value'}), color}},
				{transform: [only], mark: {type: 'point', filled: true, size: 30, opacity: 1, clip: Boolean(lim)},
					encoding: {x, y: y({field: 'value'}), color, tooltip}},
			];
			const same = k && lim && lims[0] && lim[0] === lims[0][0] && lim[1] === lims[0][1];
			if (lo < 0 && 0 < hi && !same) {  // below the lines; that of the right axis, dotted in its colour
				const zero = k ? {color: c, strokeDash: [2, 3]} : {color: MO.css('--baseline') || '#888888'};
				layer.unshift({data: {values: [{}]}, mark: Object.assign({type: 'rule', strokeWidth: 1}, zero),
					encoding: {y: y({datum: 0})}});
			}
			return {layer};
		};
		const spec = {data: {values: data}, width: 'container', height: 280};
		return two ? Object.assign(spec, {layer: [axis(0), axis(1)], resolve: {scale: {y: 'independent'}}}) :
			Object.assign(spec, axis(0));
	}

	// A profile along a line (transect): the variable against the distance, over the elevation in grey
	function transectSpec(rows, result) {
		const data = rows.map((r) => ({...r, km: r.distance_m / 1000}));
		return {
			data: {values: data}, width: 'container', height: 260, resolve: {scale: {y: 'independent'}},
			layer: [
				{mark: {type: 'area', color: '#bdbdbd', opacity: 0.5},
					encoding: {x: {field: 'km', type: 'quantitative', title: 'Distance along the line (km)'},
						y: {field: 'elevation', type: 'quantitative', title: 'Elevation (m)', axis: {orient: 'right'},
							scale: {zero: false}}}},
				{mark: {type: 'line', point: true, color: '#1f77b4'},
					encoding: {x: {field: 'km', type: 'quantitative'},
						y: {field: 'value', type: 'quantitative', title: result.ylabel || result.unit || 'Value',
							scale: {zero: false}},
						tooltip: [{field: 'km', title: 'km', format: '.2f'}, {field: 'value', title: 'Value', format: '.4~g'},
							{field: 'elevation', title: 'Elevation (m)', format: '.0f'}]}},
			],
		};
	}

	// The statistics of each zone (region_stats with zones: e.g. the elevation bands): the median (or else the mean, or
	// the first statistic) with the band of the percentiles 25 and 75 (or else 5 and 95) when they are there, in grey;
	// the legend says which
	function zonesSpec(rows, result) {
		const stats = result.stats || [];
		const mid = ['p50', 'median', 'mean'].find((s) => stats.includes(s)) || stats[0] || 'mean';
		const band = stats.includes('p25') && stats.includes('p75') ? ['p25', 'p75'] :
			stats.includes('p5') && stats.includes('p95') ? ['p5', 'p95'] : null;
		const order = [...new Set(rows.map((r) => r.zone_label))];
		const x = {field: 'zone_label', type: 'ordinal', sort: order, title: null, axis: {labelAngle: -20}};
		const name = COLUMNS[mid] || mid;
		const spread = band && `Percentiles ${band[0].slice(1)} to ${band[1].slice(1)}`;
		const scale = {domain: band ? [name, spread] : [name], range: [palette()[0], '#9e9e9e']};
		const layer = [{mark: {type: 'line', point: true}, encoding: {x,
			y: {field: mid, type: 'quantitative', title: result.ylabel || result.unit || mid, scale: {zero: false}},
			color: {datum: name, scale},
			tooltip: [{field: 'zone_label', title: 'Zone'}, {field: mid, title: name, format: '.4~g'},
				...(band || []).map((s) => ({field: s, title: COLUMNS[s] || s, format: '.4~g'})),
				{field: 'n_pixels', title: 'Pixels'}]}}];
		if (band) layer.unshift({mark: {type: 'area', opacity: 0.3}, encoding: {x,
			y: {field: band[0], type: 'quantitative'}, y2: {field: band[1]}, color: {datum: spread, scale}}});
		return {data: {values: rows}, width: 'container', height: 240, layer};
	}

	// The feature of each row of an area by class (a function of the row), as the panels of its chart of Python: a new
	// one where the region changes or a class comes again; those with the same name numbered ('Sierra Nevada (2)')
	function features(rows) {
		const of = new Map(), seen = new Map();
		let name, labels;
		rows.forEach((r, i) => {
			if (!i || r.region !== rows[i - 1].region || labels.has(r.label)) {
				seen.set(r.region, (seen.get(r.region) || 0) + 1);
				name = seen.get(r.region) > 1 ? `${r.region} (${seen.get(r.region)})` : r.region;
				labels = new Set();
			}
			labels.add(r.label);
			of.set(r, name);
		});
		return (r) => of.get(r);
	}

	function burnTiles(rows, result) {
		const sum = (f) => rows.filter(f).reduce((s, r) => s + (r.ha || 0), 0);
		if (burnIndex(rows, result) === 'RdNBR') {  // the classes of Miller & Thode 2007: unchanged, low, moderate, high
			return el('div', {class: 'stats'},
				el('div', {class: 'stat'}, el('div', {class: 'label'}, `Changed area (RdNBR ≥ ${result.burned_min ?? 0.069})`),
					el('div', {class: 'value'}, `${MO.round(sum((r) => r.class >= 1))} ha`)),
				el('div', {class: 'stat'}, el('div', {class: 'label'}, 'Moderate or high severity'),
					el('div', {class: 'value'}, `${MO.round(sum((r) => r.class >= 2))} ha`)),
				el('div', {class: 'stat'}, el('div', {class: 'label'}, 'Unchanged'),
					el('div', {class: 'value'}, `${MO.round(sum((r) => r.class === 0))} ha`)));
		}
		return el('div', {class: 'stats'},
			el('div', {class: 'stat'}, el('div', {class: 'label'}, 'Burned area (dNBR ≥ 0.1)'),
				el('div', {class: 'value'}, `${MO.round(sum((r) => r.class >= 1))} ha`)),
			el('div', {class: 'stat'}, el('div', {class: 'label'}, 'Moderate or high severity'),
				el('div', {class: 'value'}, `${MO.round(sum((r) => r.class >= 2))} ha`)),
			el('div', {class: 'stat'}, el('div', {class: 'label'}, 'Unburned'),
				el('div', {class: 'value'}, `${MO.round(sum((r) => r.class === 0))} ha`)),
			el('div', {class: 'stat'}, el('div', {class: 'label'}, 'Regrowth (dNBR < −0.1)'),
				el('div', {class: 'value'}, `${MO.round(sum((r) => r.class < 0))} ha`)));
	}

	function table(rows, kind) {
		const all = Object.keys(rows[0] || {});
		const cols = (TABLES[kind] || (RBR_BASE.every((c) => all.includes(c)) ? RBR_STATS : all))
			.filter((c) => rows.length && c in rows[0]);
		const cell = (c, v) => c === 'significant' ? (v ? 'yes' : 'no') : c === 'p_value' ? MO.pValue(v) :
			typeof v === 'number' ? (['n', 'n_images', 'n_pixels', 'first_year', 'last_year', 'class', 'n_reference', 'n_other',
				'doy', 'n_years'].includes(c) ? String(v) : MO.num(v)) : (v ?? '–');
		return el('div', {class: 'table-wrap'}, el('table', {class: 'data'},
			el('thead', {}, el('tr', {}, cols.map((c) => el('th', {scope: 'col'}, (HEADS[kind] || {})[c] || COLUMNS[c] || c)))),
			el('tbody', {}, rows.map((r) => el('tr', {}, cols.map((c) => el('td', {}, cell(c, r[c]))))))));
	}

	// Draw the chart of RESULT (its CSV is BASE + result.csv) in CONTAINER; returns its rows.
	async function render(container, result, base) {
		const rows = parse(await MO.text(base + result.csv));
		const kind = result.chart;
		// the region of each row; of an area by class, its feature (one chart each, also those with the same name)
		const regionOf = kind === 'areas' ? features(rows) : (r) => r.region;
		const regions = [...new Set(rows.map(regionOf))];
		const box = el('div', {class: 'chart'});
		const draw = async (subset) => {
			box.replaceChildren();
			narrow = (box.clientWidth || container.clientWidth) < 520;
			const parts = new Set(subset.map((r) => r.key)).size;
			if (kind === 'series') return embed(box, seriesSpec(subset, result));
			if (kind === 'trends' && parts > 1) return embed(box, trendsSpec(subset, result));
			if (kind === 'trends') return box.append(...trendTiles(subset, result));
			if (kind === 'comparison') return embed(box, comparisonSpec(subset, result));
			if (kind === 'areas') return embed(box, areasSpec(subset, result));
			if (kind === 'transect') return embed(box, transectSpec(subset, result));
			if (kind === 'doy') return embed(box, doySpec(subset, result));
			if (kind === 'doy_profile') return embed(box, doyProfileSpec(subset, result));
			if (kind === 'zones') return embed(box, zonesSpec(subset, result));
			if (kind === 'transitions') {  // its Sankey diagram (of the first region, by Python), the pairs of classes
				if (result.png && MO.safePath(result.png) && (regions.length < 2 || subset[0]?.region === regions[0])) {
					box.append(el('img', {class: 'sankey', src: base + result.png, loading: 'lazy',
						alt: `${result.title}: Sankey diagram of the changes of the broad land covers` +
							(regions.length > 1 ? ` (${regions[0]})` : '')}));
				}
				return box.append(table(subset.filter((r) => r.ha > 0), kind));
			}
			if (kind === 'burn_severity') {
				box.append(burnTiles(subset, result));
				const inner = el('div');
				box.append(inner);
				return embed(inner, burnSpec(subset, result));
			}
			return box.append(table(subset, kind));
		};
		let current = rows;
		if (regions.length > 1 &&
			['comparison', 'burn_severity', 'areas', 'transitions', 'zones', 'doy', 'doy_profile'].includes(kind) ||
			regions.length > 1 && kind === 'trends' && new Set(rows.map((r) => r.key)).size > 1) {
			const id = `c-${result.id}-region`;
			current = rows.filter((r) => regionOf(r) === regions[0]);
			container.append(el('div', {class: 'map-controls'}, el('div', {class: 'field grow'},
				el('label', {for: id}, 'Region'),
				el('select', {id, onchange: (e) => { current = rows.filter((r) => regionOf(r) === e.target.value); draw(current); }},
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
