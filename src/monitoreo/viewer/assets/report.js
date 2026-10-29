// A report (report.html?id=<id>): its texts, a map or a chart for each result with its downloads and the call that
// produced it, the downloads of the report and how to cite it.
'use strict';

(async () => {
	const {el} = MO;
	const main = document.getElementById('report');
	const id = new URLSearchParams(location.search).get('id') || '';
	MO.json('catalog.json').then((c) => MO.footer(c.about, c.license)).catch(() => {});
	if (!/^[a-z0-9][a-z0-9-]*$/.test(id)) {
		MO.fail(main, 'Falta el informe: vuelva al catálogo y elija uno.');
		return;
	}
	const base = `reports/${id}/`;
	let report;
	try {
		report = await MO.json(`${base}report.json`);
	} catch (e) {
		MO.fail(main, `No existe el informe «${id}» o no se puede leer (${e.message}).`);
		return;
	}
	const region = report.region || {};
	document.title = `${report.title} · ${region.name || ''} · Resultados de MonitorEO`;
	const files = new Map((report.files || []).map((f) => [f.path, f]));
	const link = (path, label, attrs) => MO.safePath(path)
		? el('a', Object.assign({class: 'button small', href: base + path, download: path.split('/').pop()}, attrs || {}),
			label + (files.has(path) ? ` · ${MO.bytes(files.get(path).bytes)}` : ''))
		: null;

	// head: region, title, facts
	const facts = [
		['Parque o zona', [region.full_name || region.name,
			region.wdpa_id && [' · ', el('a', {href: `https://www.protectedplanet.net/${encodeURIComponent(region.wdpa_id)}`}, `WDPA ${region.wdpa_id}`)]]],
		region.area_km2 && ['Superficie', `${MO.num(region.area_km2)} km²`],
		['Variables', (report.variables || []).map((v, i) => [i ? '; ' : '', `${v.variable} de ${v.sensor || ''}`.trim(), v.name ? ` (${v.name})` : ''])],
		report.periods?.length && ['Periodos', report.periods.map(MO.period).join('; ')],
		['Análisis', (report.analyses || []).map((a) => a.name).join(', ')],
		['Publicado', MO.date(report.published)],
		['Autoría', (report.authors || []).join('; ')],
		report.collection && ['Serie', report.collection],
		report.license && ['Licencia', MO.license(report.license)],
	].filter(Boolean);
	const head = el('header', {class: 'report-head'},
		el('a', {class: 'back', href: './'}, '← Catálogo de resultados'),
		el('div', {class: 'kicker'}, region.name || ''),
		el('h1', {}, report.title),
		el('dl', {class: 'facts'}, facts.map(([k, v]) => el('div', {}, el('dt', {}, k), el('dd', {}, v)))));

	const parts = [head];
	if (report.summary) parts.push(el('p', {class: 'lead'}, report.summary));
	if (report.question && report.question !== report.title) parts.push(el('p', {}, el('strong', {}, 'Pregunta: '), report.question));
	if (report.answer) parts.push(el('section', {class: 'prose'}, el('h2', {}, 'Resultado'), MO.paragraphs(report.answer)));

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
				content.append(el('p', {class: 'map-error'}, `No se puede dibujar el mapa: ${e.message}`));
			}
			tools.append(...[link(r.cog, 'Descargar el GeoTIFF', {title: 'Cloud Optimized GeoTIFF, con todas las capas'})].filter(Boolean));
		} else if (r.kind === 'chart' && MO.safePath(r.csv)) {
			const tableBox = el('div');
			let table = null;
			const toggle = el('button', {class: 'button small', type: 'button', 'aria-expanded': 'false', disabled: true}, 'Ver la tabla');
			pending.push(MO.chart.render(content, r, base).then((res) => {
				toggle.disabled = false;
				toggle.addEventListener('click', () => {
					const open = toggle.getAttribute('aria-expanded') === 'true';
					if (!table) table = res.table();
					tableBox.replaceChildren(...(open ? [] : [table]));
					toggle.setAttribute('aria-expanded', String(!open));
					toggle.textContent = open ? 'Ver la tabla' : 'Ocultar la tabla';
				});
			}).catch((e) => content.append(el('p', {class: 'map-error'}, `No se puede dibujar el gráfico: ${e.message}`))));
			content.append(tableBox);
			tools.append(...[toggle, link(r.csv, 'Descargar el CSV'), r.png && link(r.png, 'Gráfico (PNG)')].filter(Boolean));
		}
		section.append(tools);
		if (r.call) {
			const args = JSON.stringify(r.call.args, null, 1);
			section.append(el('details', {class: 'call'},
				el('summary', {}, 'Cómo se calculó'),
				el('p', {}, 'Con la herramienta ', el('code', {}, r.call.tool), ' de MonitorEO (servidor MCP, plugin de QGIS, Python y R). En Python:'),
				el('pre', {}, `import monitoreo.services as mo\nmo.init('<proyecto de Earth Engine>')\n${r.call.python}`),
				el('p', {}, 'Argumentos de la llamada (JSON):'),
				el('pre', {}, args)));
		}
		parts.push(section);
	}

	if (report.method) parts.push(el('section', {class: 'prose'}, el('h2', {}, 'Método'), MO.paragraphs(report.method)));
	for (const s of report.sections || []) parts.push(el('section', {class: 'prose'}, el('h2', {}, s.title), MO.paragraphs(s.text)));

	// downloads
	const rows = (report.files || []).filter((f) => MO.safePath(f.path)).map((f) => el('tr', {},
		el('td', {}, f.title), el('td', {class: 'type'}, f.type || ''), el('td', {class: 'size'}, MO.bytes(f.bytes)),
		el('td', {class: 'get'}, el('a', {class: 'button small', href: base + f.path, download: f.path.split('/').pop(),
			'aria-label': `Descargar ${f.title}`}, 'Descargar'))));
	rows.push(el('tr', {}, el('td', {}, 'Descripción del informe y de cada resultado, con sus llamadas (report.json)'),
		el('td', {class: 'type'}, 'JSON'), el('td', {class: 'size'}, ''),
		el('td', {class: 'get'}, el('a', {class: 'button small', href: `${base}report.json`}, 'Abrir'))));
	parts.push(el('section', {class: 'block'}, el('h2', {}, 'Descargas'), el('table', {class: 'downloads'}, el('tbody', {}, rows))));

	const url = location.href.split('#')[0];
	parts.push(el('section', {class: 'prose'}, el('h2', {}, 'Cómo citar'),
		el('p', {}, `${(report.authors || []).join('; ')} (${report.published.slice(0, 4)}). ${region.full_name || region.name}: ` +
			`${report.title} Resultados de MonitorEO-OBSNEV, ${MO.date(report.published)}. `, el('a', {href: url}, url)),
		report.license && el('p', {}, 'Los datos y mapas de este informe se publican con licencia ', MO.license(report.license),
			report.license.text ? `: ${report.license.text}` : '.')));

	main.replaceChildren(...parts);
	if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
	await Promise.allSettled(pending);
})();
