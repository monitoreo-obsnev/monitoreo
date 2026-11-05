// Viewer of results of MonitorEO-OBSNEV: helpers of the catalogue and the report pages (namespace MO).
// The texts come from catalog.json and report.json, written by monitoreo.publish; they are always shown as text.
'use strict';

const MO = (() => {
	const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
	// the names of the analyses of monitoreo.publish by their id (a report published by an older version has them in
	// Spanish)
	const ANALYSES = {series: 'Time series', trend: 'Trend', comparison: 'Comparison of periods',
		burn_severity: 'Burn severity', map: 'Map'};

	async function json(url) {
		const r = await fetch(url, {cache: 'no-cache'});
		if (!r.ok) throw new Error(`${url}: ${r.status} ${r.statusText}`);
		return r.json();
	}

	async function text(url) {
		const r = await fetch(url, {cache: 'no-cache'});
		if (!r.ok) throw new Error(`${url}: ${r.status} ${r.statusText}`);
		return r.text();
	}

	// An element with attributes (on* are listeners) and children (nodes or texts, never HTML).
	function el(tag, attrs, ...children) {
		const e = document.createElement(tag);
		for (const [k, v] of Object.entries(attrs || {})) {
			if (v === null || v === undefined || v === false) continue;
			if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
			else if (k === 'class') e.className = v;
			else e.setAttribute(k, v === true ? '' : v);
		}
		for (const c of children.flat(Infinity)) {
			if (c === null || c === undefined || c === false) continue;
			e.append(c instanceof Node ? c : String(c));
		}
		return e;
	}

	// Paragraphs of a text (separated by a blank line).
	function paragraphs(t) {
		return String(t || '').split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean).map((p) => el('p', {}, p));
	}

	// A path of a file of the site: relative, without '..' (the files of report.json).
	function safePath(p) {
		return typeof p === 'string' && /^[A-Za-z0-9._\-/]+$/.test(p) && !p.split('/').includes('..') && !p.startsWith('/');
	}

	const nf = new Intl.NumberFormat('en-US', {maximumSignificantDigits: 4});

	// A number in English with SIG significant digits (default 4), without -0.
	function num(v, sig) {
		if (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) return '–';
		const x = Number(v);
		if (x === 0) return '0';
		const f = sig ? new Intl.NumberFormat('en-US', {maximumSignificantDigits: sig}) : nf;
		return f.format(x).replace(/^-/, '−');
	}

	// A number rounded to integer (or to one decimal below 10), e.g. hectares.
	function round(v) {
		if (v === null || v === undefined || Number.isNaN(Number(v))) return '–';
		const x = Number(v);
		return new Intl.NumberFormat('en-US', {maximumFractionDigits: Math.abs(x) < 10 ? 1 : 0}).format(x).replace(/^-/, '−');
	}

	function signed(v, sig) {
		const s = num(v, sig);
		return Number(v) > 0 ? `+${s}` : s;
	}

	function pValue(p) {
		if (p === null || p === undefined || p === '') return '–';
		return Number(p) < 0.001 ? '< 0.001' : num(p, 2);
	}

	function bytes(n) {
		if (n < 1024) return `${n} B`;
		if (n < 1024 * 1024) return `${num(n / 1024, 3)} KB`;
		return `${num(n / 1024 / 1024, 3)} MB`;
	}

	function date(d) {
		const [y, m, day] = String(d).slice(0, 10).split('-');
		return `${Number(day)} ${MONTHS[Number(m) - 1]} ${y}`;
	}

	// '2001-2024', '2023' or '15 May 2023 – 14 Aug 2023', as monitoreo.publish.period_text.
	function period(p) {
		const [a, b] = p;
		if (a.slice(5) === '01-01' && b.slice(5) === '12-31') return a.slice(0, 4) === b.slice(0, 4) ? a.slice(0, 4) : `${a.slice(0, 4)}-${b.slice(0, 4)}`;
		return `${date(a)} – ${date(b)}`;
	}

	function css(name) {
		return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
	}

	// The name of an analysis {id, name} of catalog.json or report.json.
	function analysis(a) {
		return ANALYSES[a.id] || a.name;
	}

	function variables(vs) {
		return (vs || []).map((v) => v.sensor ? `${v.variable} · ${v.sensor}` : v.variable);
	}

	// The name of a licence {name, url} of catalog.json or report.json, with a link to its text.
	function license(lic) {
		return /^https:\/\/\S+$/.test(lic.url || '') ? el('a', {href: lic.url, rel: 'license'}, lic.name) : lic.name;
	}

	// The alternative text of each logo of monitoreo.about, by its file name.
	const LOGO_ALT = {
		'monitoreo_obsnev.png': 'Sierra Nevada Global Change Observatory, University of Granada, Ministry of Science, Innovation and Universities, co-funded by the European Union, State Research Agency and Regional Government of Andalusia',
		'nevadeo_feder.jpg': 'Co-funded by the European Union, Government of Spain (European Funds), Regional Government of Andalusia and University of Granada',
		'biodiversa.png': 'Biodiversa+, European Biodiversity Partnership'};

	// The footer: description, acknowledgements, citation and logos of monitoreo.about, and the licence of the site
	// (in catalog.json).
	function footer(about, lic) {
		const f = document.querySelector('.site-footer .wrap');
		if (!f || !about) return;
		const doi = /^10\.\d{4,9}\/\S+$/.test(about.doi || '') && `https://doi.org/${about.doi}`;
		f.replaceChildren(
			el('h2', {}, about.name || 'MonitorEO-OBSNEV'),
			el('p', {}, about.description),
			el('p', {}, about.acknowledgements),
			about.citation && el('p', {}, el('strong', {}, 'How to cite MonitorEO: '),
				doi ? [about.citation.replace(doi, ''), el('a', {href: doi}, doi)] : about.citation),
			lic && el('p', {}, 'The data and maps of this site are published under the license ', license(lic),
				', unless a report says another one', lic.text ? `: ${lic.text}` : '.', ' Each report says how to cite it.'),
			el('div', {class: 'logos'}, (about.logos || []).filter(safePath).map(src =>
				el('img', {src, alt: LOGO_ALT[src.split('/').pop()] || '', loading: 'lazy'}))),
			el('div', {class: 'footer-links'},
				about.manual && el('a', {href: about.manual}, 'Manual'),
				about.repository && el('a', {href: about.repository}, 'Code (GPL-3.0)')));
	}

	function fail(container, message) {
		container.replaceChildren(el('div', {class: 'error', role: 'alert'}, message));
	}

	return {json, text, el, paragraphs, safePath, num, round, signed, pValue, bytes, date, period, css, analysis, variables, license, footer, fail, MONTHS};
})();
