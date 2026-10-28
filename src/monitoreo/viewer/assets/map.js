// Maps of the reports: the Cloud Optimized GeoTIFF of a result drawn by OpenLayers (WebGL) with the legend of one of
// its bands, over a base map, and the values of every band of a pixel on click, read by geotiff.js at full
// resolution (the overviews of the COG only serve to draw it).
'use strict';

MO.map = (() => {
	const {el} = MO;
	const images = new Map();
	const maps = [];  // the maps of the page (to inspect them from the console)
	const NOT_SIGNIFICANT = '#c9c8c2';
	const BASEMAPS = [
		['osm', 'Mapa (OpenStreetMap)', () => new ol.source.OSM()],
		['pnoa', 'Ortofoto PNOA (España)', () => new ol.source.XYZ({
			url: 'https://www.ign.es/wmts/pnoa-ma?request=GetTile&service=WMTS&VERSION=1.0.0&Layer=OI.OrthoimageCoverage' +
				'&Style=default&Format=image/jpeg&TileMatrixSet=GoogleMapsCompatible&TileMatrix={z}&TileRow={y}&TileCol={x}',
			attributions: 'Ortofoto PNOA © Instituto Geográfico Nacional de España', maxZoom: 19})],
		['none', 'Sin mapa de fondo', null],
	];

	const rgba = (hex, a = 1) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).concat(a);

	// Colour expression of OpenLayers of a band (its index, from 1) with its legend.
	function colour(band, index) {
		const L = band.legend, v = ['band', index];
		if (L.type === 'categories') return ['match', v, ...L.classes.flatMap((c) => [c.value, rgba(c.color)]), [0, 0, 0, 0]];
		const n = L.palette.length;
		return ['interpolate', ['linear'], v, ...L.palette.flatMap((c, k) => [L.min + (L.max - L.min) * k / (n - 1), rgba(c)])];
	}

	function style(result, band, dim) {
		const names = result.bands.map((b) => b.name);
		let c = colour(band, names.indexOf(band.name) + 1);
		const sig = result.significance;
		if (dim && sig) c = ['case', ['>=', ['band', names.indexOf(sig.band) + 1], sig.alpha], rgba(NOT_SIGNIFICANT), c];
		// the source adds an alpha band after the bands of the file: 0 where they are NoData
		return {color: ['case', ['==', ['band', names.length + 1], 0], [0, 0, 0, 0], c]};
	}

	function legend(box, result, band, dim) {
		const L = band.legend;
		const title = band.unit ? `${band.label} (${band.unit})` : band.label;
		const items = [el('div', {class: 'legend-title'}, title)];
		if (L.type === 'categories') {
			for (const c of L.classes) items.push(el('span', {class: 'legend-item'}, el('span', {class: 'swatch', style: `background:${c.color}`}), c.label));
		} else {
			const ticks = [L.min, L.max];
			if (L.min < 0 && L.max > 0) ticks.splice(1, 0, 0);
			// the values beyond the ends of the ramp have the colours of the ends (but τ goes from -1 to 1)
			const label = (v, i) => {
				const s = MO.num(v, 3);
				if (band.name === 'tau' || i === 1 && ticks.length === 3) return s;
				return i === 0 ? `≤ ${s}` : `≥ ${s}`;
			};
			items.push(el('div', {class: 'legend-ramp'},
				el('div', {class: 'legend-bar', style: `background:linear-gradient(to right,${L.palette.join(',')})`}),
				el('div', {class: 'legend-ticks'}, ticks.map((v, i) => el('span', {}, band.name === 'p_value' && i === 0 ? '0' : label(v, i))))));
		}
		if (dim && result.significance) {
			items.push(el('span', {class: 'legend-item'}, el('span', {class: 'swatch', style: `background:${NOT_SIGNIFICANT}`}),
				`Sin tendencia significativa (p ≥ ${MO.num(result.significance.alpha)})`));
		}
		box.replaceChildren(...items);
	}

	function format(band, v) {
		if (v === null || v === undefined || Number.isNaN(v)) return 'sin datos';
		if (band.legend.type === 'categories') {
			const c = band.legend.classes.find((x) => x.value === Math.round(v));
			return c ? c.label : MO.num(v);
		}
		if (band.name === 'p_value') return MO.pValue(v);
		if (band.name === 'n') return MO.num(v);
		return MO.num(v, 3) + (band.unit && band.unit !== 'por año' ? ` ${band.unit}` : '');
	}

	// Values of every band of the pixel of the COG at COORD (web Mercator), or null outside it.
	async function query(url, result, coord) {
		if (!images.has(url)) images.set(url, GeoTIFF.fromUrl(url, {allowFullFile: true}).then((t) => t.getImage()));
		const img = await images.get(url);
		const [x, y] = ol.proj.transform(coord, 'EPSG:3857', result.crs);
		const [ox, oy] = img.getOrigin(), [rx, ry] = img.getResolution();
		const col = Math.floor((x - ox) / rx), row = Math.floor((y - oy) / ry);
		if (col < 0 || row < 0 || col >= img.getWidth() || row >= img.getHeight()) return null;
		const data = await img.readRasters({window: [col, row, col + 1, row + 1]});
		return result.bands.map((b, i) => {
			const v = data[i][0];
			return v === result.nodata || !Number.isFinite(v) ? null : v;
		});
	}

	function render(container, result, base) {
		const url = new URL(base + result.cog, location.href).href;
		if (!window.ol || !window.proj4 || !window.GeoTIFF) {
			container.append(el('p', {class: 'map-error'}, 'No se han podido cargar las bibliotecas del mapa (OpenLayers, proj4, geotiff.js).'));
			return;
		}
		if (!ol.proj.get(result.crs)) {
			proj4.defs(result.crs, result.proj4);
			ol.proj.proj4.register(proj4);
		}
		let band = result.bands.find((b) => b.name === result.band) || result.bands[0];
		let dim = Boolean(result.significance);
		const source = new ol.source.GeoTIFF({
			sources: [{url, nodata: result.nodata}], normalize: false, interpolate: false, projection: result.crs,
			sourceOptions: {allowFullFile: true}});
		const layer = new ol.layer.WebGLTile({source, style: style(result, band, dim), opacity: 0.9});
		const background = new ol.layer.Tile({source: BASEMAPS[0][2]()});
		const target = el('div', {class: 'map', role: 'region', 'aria-label': `Mapa: ${result.title}`});
		const box = el('div', {class: 'legend'});
		const popup = el('div', {class: 'popup'});
		const overlay = new ol.Overlay({element: popup, positioning: 'bottom-center', offset: [0, -12], autoPan: {animation: {duration: 200}}});

		const id = `m-${result.id}`;
		const controls = el('div', {class: 'map-controls'});
		if (result.bands.length > 1) {
			controls.append(el('div', {class: 'field grow'}, el('label', {for: `${id}-band`}, 'Capa'),
				el('select', {id: `${id}-band`, onchange: (e) => {
					band = result.bands.find((b) => b.name === e.target.value);
					layer.setStyle(style(result, band, dim));
					legend(box, result, band, dim);
				}}, result.bands.map((b) => el('option', {value: b.name, selected: b.name === band.name}, b.unit ? `${b.label} (${b.unit})` : b.label)))));
		}
		if (result.significance) {
			controls.append(el('label', {class: 'check'}, el('input', {type: 'checkbox', checked: dim, onchange: (e) => {
				dim = e.target.checked;
				layer.setStyle(style(result, band, dim));
				legend(box, result, band, dim);
			}}), `Gris donde la tendencia no es significativa (p ≥ ${MO.num(result.significance.alpha)})`));
		}
		controls.append(
			el('div', {class: 'field'}, el('label', {for: `${id}-base`}, 'Mapa de fondo'),
				el('select', {id: `${id}-base`, onchange: (e) => {
					const make = BASEMAPS.find((b) => b[0] === e.target.value)[2];
					background.setVisible(Boolean(make));
					if (make) background.setSource(make());
				}}, BASEMAPS.map(([v, label]) => el('option', {value: v}, label)))),
			el('div', {class: 'field'}, el('label', {for: `${id}-opacity`}, 'Opacidad'),
				el('input', {id: `${id}-opacity`, type: 'range', min: 0, max: 1, step: 0.05, value: 0.9,
					oninput: (e) => layer.setOpacity(Number(e.target.value))})));
		container.append(controls, target, box,
			el('p', {class: 'map-note'}, 'Pulse en el mapa para ver los valores de todas las capas en ese píxel; acerque con los botones o con Ctrl (⌘) y la rueda del ratón' +
				(result.resolution ? ` (píxeles de ${MO.num(result.resolution)} m` : '') +
				(result.images ? `; media de ${result.images} imágenes)` : result.resolution ? ')' : '') + '.'));
		legend(box, result, band, dim);

		const extent = ol.proj.transformExtent(result.bounds, 'EPSG:4326', 'EPSG:3857');
		let map;
		try {
			map = new ol.Map({
				target, layers: [background, layer], overlays: [overlay],
				view: new ol.View({projection: 'EPSG:3857', maxZoom: 19}),
				// the wheel scrolls the page; with Ctrl or ⌘ it zooms the map
				interactions: ol.interaction.defaults.defaults({mouseWheelZoom: false}).extend([
					new ol.interaction.MouseWheelZoom({condition: ol.events.condition.platformModifierKeyOnly})]),
				controls: ol.control.defaults.defaults({attributionOptions: {collapsible: true},
					zoomOptions: {zoomInTipLabel: 'Acercar', zoomOutTipLabel: 'Alejar'}}).extend([
					new ol.control.ZoomToExtent({extent, label: '⤢', tipLabel: 'Ver todo el mapa'}),
					new ol.control.ScaleLine({units: 'metric'}), new ol.control.FullScreen({tipLabel: 'Pantalla completa'})]),
			});
		} catch (e) {
			target.replaceChildren(el('p', {class: 'map-error'}, `Este navegador no puede dibujar el mapa (WebGL): ${e.message}`));
			return;
		}
		// fit the map when it gets its size (the page adds it to the document later, which OpenLayers does not see)
		new ResizeObserver(() => map.updateSize()).observe(target);
		let fitted = false;
		const fit = () => {
			const size = map.getSize();
			if (fitted || !size || !size[0] || !size[1]) return;
			fitted = true;
			map.getView().fit(extent, {padding: [16, 16, 16, 16]});
		};
		map.on('change:size', fit);
		fit();
		maps.push(map);
		source.on('tileloaderror', () => target.dataset.error = 'tiles');

		const close = () => overlay.setPosition(undefined);
		map.on('singleclick', async (e) => {
			let values;
			try {
				values = await query(url, result, e.coordinate);
			} catch (err) {
				values = undefined;
				popup.replaceChildren(el('button', {class: 'close', 'aria-label': 'Cerrar', onclick: close}, '×'), `No se puede leer el píxel: ${err.message}`);
				overlay.setPosition(e.coordinate);
				return;
			}
			if (!values || values.every((v) => v === null)) {
				close();
				return;
			}
			const [lon, lat] = ol.proj.toLonLat(e.coordinate);
			popup.replaceChildren(
				el('button', {class: 'close', 'aria-label': 'Cerrar', onclick: close}, '×'),
				el('table', {}, result.bands.map((b, i) => el('tr', {class: b.name === band.name ? 'current' : null},
					el('td', {}, b.label), el('td', {}, format(b, values[i]))))),
				el('div', {class: 'where'}, `${lat.toFixed(5)}, ${lon.toFixed(5)}`));
			overlay.setPosition(e.coordinate);
		});
		map.on('pointermove', (e) => {
			if (e.dragging) return;
			target.style.cursor = layer.getData(e.pixel) ? 'crosshair' : '';
		});
		return map;
	}

	return {render, query, maps};
})();
