// A report (report.html?id=<id>): its texts, a map or a chart for each result with its downloads and the call that
// produced it, the downloads of the report and how to cite it.
'use strict';

(async () => {
	const {el} = MO;
	const main = document.getElementById('report');
	const id = new URLSearchParams(location.search).get('id') || '';
	MO.json('catalog.json').then((c) => MO.footer(c.about, c.license)).catch(() => {});
	if (!/^[a-z0-9][a-z0-9-]*$/.test(id)) {
		MO.fail(main, 'No report given: go back to the catalog and choose one.');
		return;
	}
	const base = `reports/${id}/`;
	let report;
	try {
		report = await MO.json(`${base}report.json`);
	} catch (e) {
		MO.fail(main, `The report “${id}” does not exist or cannot be read (${e.message}).`);
		return;
	}
	const region = report.region || {};
	document.title = `${report.title} · ${region.name || ''} · Results of MonitorEO`;
	const files = new Map((report.files || []).map((f) => [f.path, f]));
	const link = (path, label, attrs) => MO.safePath(path)
		? el('a', Object.assign({class: 'button small', href: base + path, download: path.split('/').pop()}, attrs || {}),
			label + (files.has(path) ? ` · ${MO.bytes(files.get(path).bytes)}` : ''))
		: null;

	// head: region, title, facts
	const facts = [
		['Park or area', [region.full_name || region.name,
			region.wdpa_id && [' · ', el('a', {href: `https://www.protectedplanet.net/${encodeURIComponent(region.wdpa_id)}`}, `WDPA ${region.wdpa_id}`)]]],
		region.area_km2 && ['Surface area', `${MO.num(region.area_km2)} km²`],
		['Variables', (report.variables || []).map((v, i) => [i ? '; ' : '', v.sensor ? `${v.variable} from ${v.sensor}` : v.variable, v.name ? ` (${v.name})` : ''])],
		report.periods?.length && ['Periods', report.periods.map(MO.period).join('; ')],
		['Analyses', (report.analyses || []).map(MO.analysis).join(', ')],
		['Published', MO.date(report.published)],
		['Authors', (report.authors || []).join('; ')],
		report.collection && ['Collection', report.collection],
		report.license && ['License', MO.license(report.license)],
	].filter(Boolean);
	const head = el('header', {class: 'report-head'},
		el('a', {class: 'back', href: './'}, '← Catalog of results'),
		el('div', {class: 'kicker'}, region.name || ''),
		el('h1', {}, report.title),
		el('dl', {class: 'facts'}, facts.map(([k, v]) => el('div', {}, el('dt', {}, k), el('dd', {}, v)))));

	const parts = [head];
	if (report.summary) parts.push(el('p', {class: 'lead'}, report.summary));
	if (report.question && report.question !== report.title) parts.push(el('p', {}, el('strong', {}, 'Question: '), report.question));
	if (report.answer) parts.push(el('section', {class: 'prose'}, el('h2', {}, 'Answer'), MO.paragraphs(report.answer)));

	// results
	const pending = [];
	for (const r of report.results || []) {
		const section = el('section', {class: 'result', id: r.id, 'aria-labelledby': `${r.id}-title`});
		section.append(el('div', {class: 'result-head'}, el('h2', {id: `${r.id}-title`}, r.title), r.caption && el('p', {}, r.caption)));
		const content = el('div', {class: 'result-body'});
		section.append(content);
		const tools = el('div', {class: 'result-tools'});
		if (r.kind === 'map' && MO.safePath(r.cog)) {
			try {
				MO.map.render(content, r, base);
			} catch (e) {
				content.append(el('p', {class: 'map-error'}, `Cannot draw the map: ${e.message}`));
			}
			tools.append(...[link(r.cog, 'Download the GeoTIFF', {title: 'Cloud Optimized GeoTIFF, with all the layers'})].filter(Boolean));
		} else if (r.kind === 'chart' && MO.safePath(r.csv)) {
			const tableBox = el('div');
			let table = null;
			const toggle = el('button', {class: 'button small', type: 'button', 'aria-expanded': 'false', disabled: true}, 'Show the table');
			pending.push(MO.chart.render(content, r, base).then((res) => {
				toggle.disabled = false;
				toggle.addEventListener('click', () => {
					const open = toggle.getAttribute('aria-expanded') === 'true';
					if (!table) table = res.table();
					tableBox.replaceChildren(...(open ? [] : [table]));
					toggle.setAttribute('aria-expanded', String(!open));
					toggle.textContent = open ? 'Show the table' : 'Hide the table';
				});
			}).catch((e) => content.append(el('p', {class: 'map-error'}, `Cannot draw the chart: ${e.message}`))));
			content.append(tableBox);
			tools.append(...[toggle, link(r.csv, 'Download the CSV'), r.png && link(r.png, 'Chart (PNG)')].filter(Boolean));
		}
		section.append(tools);
		if (r.call) {
			const args = JSON.stringify(r.call.args, null, 1);
			section.append(el('details', {class: 'call'},
				el('summary', {}, 'How it was computed'),
				el('p', {}, 'With the tool ', el('code', {}, r.call.tool), ' of MonitorEO (MCP server, QGIS plugin, Python and R). In Python:'),
				el('pre', {}, `import monitoreo.services as mo\nmo.init('<Google Cloud project>')\n${r.call.python}`),
				el('p', {}, 'Arguments of the call (JSON):'),
				el('pre', {}, args)));
		}
		parts.push(section);
	}

	if (report.method) parts.push(el('section', {class: 'prose'}, el('h2', {}, 'Method'), MO.paragraphs(report.method)));
	for (const s of report.sections || []) parts.push(el('section', {class: 'prose'}, el('h2', {}, s.title), MO.paragraphs(s.text)));

	// downloads
	const rows = (report.files || []).filter((f) => MO.safePath(f.path)).map((f) => el('tr', {},
		el('td', {}, f.title), el('td', {class: 'type'}, f.type || ''), el('td', {class: 'size'}, MO.bytes(f.bytes)),
		el('td', {class: 'get'}, el('a', {class: 'button small', href: base + f.path, download: f.path.split('/').pop(),
			'aria-label': `Download ${f.title}`}, 'Download'))));
	rows.push(el('tr', {}, el('td', {}, 'Description of the report and of each result, with their calls (report.json)'),
		el('td', {class: 'type'}, 'JSON'), el('td', {class: 'size'}, ''),
		el('td', {class: 'get'}, el('a', {class: 'button small', href: `${base}report.json`}, 'Open'))));
	parts.push(el('section', {class: 'block'}, el('h2', {}, 'Downloads'), el('table', {class: 'downloads'}, el('tbody', {}, rows))));

	const url = location.href.split('#')[0];
	parts.push(el('section', {class: 'prose'}, el('h2', {}, 'How to cite'),
		el('p', {}, `${(report.authors || []).join('; ')} (${report.published.slice(0, 4)}). ${region.full_name || region.name}: ` +
			`${report.title} Results of MonitorEO-OBSNEV, ${MO.date(report.published)}. `, el('a', {href: url}, url)),
		report.license && el('p', {}, 'The data and maps of this report are published under the license ', MO.license(report.license),
			report.license.text ? `: ${report.license.text}` : '.')));

	main.replaceChildren(...parts);
	if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
	await Promise.allSettled(pending);
})();
