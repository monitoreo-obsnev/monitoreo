// Catalogue of the reports (catalog.json): a card per report, with filters by park, variable, analysis and year of
// the data and a search box. The filters are kept in the address (?parque=...&anio=...), to share a selection.
'use strict';

(async () => {
	const {el} = MO;
	const cards = document.getElementById('cards');
	const form = document.getElementById('filters');
	const count = document.getElementById('count');
	let catalog;
	try {
		catalog = await MO.json('catalog.json');
	} catch (e) {
		MO.fail(cards, `No se puede leer el catálogo (catalog.json): ${e.message}`);
		return;
	}
	MO.footer(catalog.about, catalog.license);
	const reports = catalog.reports || [];

	const fold = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
	const yearsOf = (r) => (r.periods || []).flatMap(([a, b]) => {
		const out = [];
		for (let y = Number(a.slice(0, 4)); y <= Number(b.slice(0, 4)); y++) out.push(y);
		return out;
	});
	for (const r of reports) {
		r._years = new Set(yearsOf(r));
		r._text = fold([r.title, r.question, r.summary, r.region?.name, r.region?.full_name, r.collection,
			...(r.keywords || []), ...(r.variables || []).flatMap((v) => [v.variable, v.name, v.sensor]),
			...(r.analyses || []).map((a) => a.name)].join(' '));
	}

	// options of the filters, from the reports
	const options = (id, pairs) => {
		const sel = document.getElementById(id);
		for (const [value, label] of pairs) sel.append(el('option', {value}, label));
	};
	const uniq = (pairs) => [...new Map(pairs).entries()];
	const byLabel = (a, b) => String(a[1]).localeCompare(String(b[1]), 'es');
	options('parque', uniq(reports.map((r) => [r.region?.name, r.region?.name])).filter(([v]) => v).sort(byLabel));
	options('variable', uniq(reports.flatMap((r) => (r.variables || []).map((v) => [v.variable, v.name ? `${v.variable} · ${v.name}` : v.variable]))).sort(byLabel));
	options('analisis', uniq(reports.flatMap((r) => (r.analyses || []).map((a) => [a.id, a.name]))).sort(byLabel));
	const years = [...new Set(reports.flatMap((r) => [...r._years]))].sort((a, b) => b - a);
	options('anio', years.map((y) => [String(y), String(y)]));

	// the filters of the address
	const params = new URLSearchParams(location.search);
	for (const name of ['q', 'parque', 'variable', 'analisis', 'anio']) {
		const input = form.elements[name];
		if (params.has(name)) input.value = params.get(name);
	}

	function card(r) {
		const thumb = r.thumbnail && MO.safePath(r.thumbnail)
			? el('img', {src: r.thumbnail, alt: `Mapa o gráfico del informe: ${r.title}`, loading: 'lazy'})
			: el('span', {class: 'none'}, 'Sin imagen');
		const span = r.years ? (r.years[0] === r.years[1] ? String(r.years[0]) : `${r.years[0]}-${r.years[1]}`) : null;
		return el('a', {class: 'card', href: `report.html?id=${encodeURIComponent(r.id)}`},
			el('div', {class: 'thumb'}, thumb),
			el('div', {class: 'card-body'},
				el('div', {class: 'kicker'}, r.region?.name || ''),
				el('h2', {}, r.title),
				r.summary && el('p', {}, r.summary),
				el('div', {class: 'meta'},
					MO.variables(r.variables).map((v) => el('span', {class: 'chip'}, v)),
					span && el('span', {class: 'chip', title: 'Años de los datos'}, span),
					(r.analyses || []).map((a) => el('span', {class: 'chip analysis'}, a.name))),
				el('div', {class: 'card-foot'}, `Publicado el ${MO.date(r.published)}` + (r.collection ? ` · ${r.collection}` : ''))));
	}

	function update() {
		const f = Object.fromEntries(new FormData(form).entries());
		const q = fold(f.q).split(/\s+/).filter(Boolean);
		const shown = reports.filter((r) =>
			(!f.parque || r.region?.name === f.parque) &&
			(!f.variable || (r.variables || []).some((v) => v.variable === f.variable)) &&
			(!f.analisis || (r.analyses || []).some((a) => a.id === f.analisis)) &&
			(!f.anio || r._years.has(Number(f.anio))) &&
			q.every((w) => r._text.includes(w)));
		cards.replaceChildren(...(shown.length ? shown.map(card) :
			[el('p', {class: 'empty'}, 'Ningún informe cumple estos filtros.')]));
		count.textContent = shown.length === reports.length
			? `${reports.length} informe${reports.length === 1 ? '' : 's'} publicado${reports.length === 1 ? '' : 's'}`
			: `${shown.length} de ${reports.length} informes`;
		const p = new URLSearchParams(Object.entries(f).filter(([, v]) => v));
		history.replaceState(null, '', p.toString() ? `?${p}` : location.pathname);
	}

	form.addEventListener('input', update);
	form.addEventListener('submit', (e) => e.preventDefault());
	form.addEventListener('reset', () => setTimeout(update));
	update();
})();
