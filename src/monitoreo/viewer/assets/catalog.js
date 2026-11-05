// Catalogue of the reports (catalog.json): a card per report, with filters by park, variable, analysis and year of
// the data and a search box. The filters are kept in the address (?area=...&year=...), to share a selection; the
// addresses of the viewer in Spanish (?parque=...&analisis=...&anio=...) are read too.
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
		MO.fail(cards, `Cannot read the catalog (catalog.json): ${e.message}`);
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
			...(r.analyses || []).flatMap((a) => [MO.analysis(a), a.name])].join(' '));
	}

	// options of the filters, from the reports
	const options = (id, pairs) => {
		const sel = document.getElementById(id);
		for (const [value, label] of pairs) sel.append(el('option', {value}, label));
	};
	const uniq = (pairs) => [...new Map(pairs).entries()];
	const byLabel = (a, b) => String(a[1]).localeCompare(String(b[1]), 'en');
	options('area', uniq(reports.map((r) => [r.region?.name, r.region?.name])).filter(([v]) => v).sort(byLabel));
	options('variable', uniq(reports.flatMap((r) => (r.variables || []).map((v) => [v.variable, v.name ? `${v.variable} · ${v.name}` : v.variable]))).sort(byLabel));
	options('analysis', uniq(reports.flatMap((r) => (r.analyses || []).map((a) => [a.id, MO.analysis(a)]))).sort(byLabel));
	const years = [...new Set(reports.flatMap((r) => [...r._years]))].sort((a, b) => b - a);
	options('year', years.map((y) => [String(y), String(y)]));

	// the filters of the address (and those of the addresses in Spanish)
	const params = new URLSearchParams(location.search);
	for (const [old, name] of [['parque', 'area'], ['analisis', 'analysis'], ['anio', 'year']]) {
		if (params.has(old) && !params.has(name)) params.set(name, params.get(old));
	}
	for (const name of ['q', 'area', 'variable', 'analysis', 'year']) {
		const input = form.elements[name];
		if (params.has(name)) input.value = params.get(name);
	}

	function card(r) {
		const thumb = r.thumbnail && MO.safePath(r.thumbnail)
			? el('img', {src: r.thumbnail, alt: `Map or chart of the report: ${r.title}`, loading: 'lazy'})
			: el('span', {class: 'none'}, 'No image');
		const span = r.years ? (r.years[0] === r.years[1] ? String(r.years[0]) : `${r.years[0]}-${r.years[1]}`) : null;
		return el('a', {class: 'card', href: `report.html?id=${encodeURIComponent(r.id)}`},
			el('div', {class: 'thumb'}, thumb),
			el('div', {class: 'card-body'},
				el('div', {class: 'kicker'}, r.region?.name || ''),
				el('h2', {}, r.title),
				r.summary && el('p', {}, r.summary),
				el('div', {class: 'meta'},
					MO.variables(r.variables).map((v) => el('span', {class: 'chip'}, v)),
					span && el('span', {class: 'chip', title: 'Years of the data'}, span),
					(r.analyses || []).map((a) => el('span', {class: 'chip analysis'}, MO.analysis(a)))),
				el('div', {class: 'card-foot'}, `Published on ${MO.date(r.published)}` + (r.collection ? ` · ${r.collection}` : ''))));
	}

	function update() {
		const f = Object.fromEntries(new FormData(form).entries());
		const q = fold(f.q).split(/\s+/).filter(Boolean);
		const shown = reports.filter((r) =>
			(!f.area || r.region?.name === f.area) &&
			(!f.variable || (r.variables || []).some((v) => v.variable === f.variable)) &&
			(!f.analysis || (r.analyses || []).some((a) => a.id === f.analysis)) &&
			(!f.year || r._years.has(Number(f.year))) &&
			q.every((w) => r._text.includes(w)));
		cards.replaceChildren(...(shown.length ? shown.map(card) :
			[el('p', {class: 'empty'}, 'No report matches these filters.')]));
		count.textContent = shown.length === reports.length
			? `${reports.length} report${reports.length === 1 ? '' : 's'} published`
			: `${shown.length} of ${reports.length} reports`;
		const p = new URLSearchParams(Object.entries(f).filter(([, v]) => v));
		history.replaceState(null, '', p.toString() ? `?${p}` : location.pathname);
	}

	form.addEventListener('input', update);
	form.addEventListener('submit', (e) => e.preventDefault());
	form.addEventListener('reset', () => setTimeout(update));
	update();
})();
