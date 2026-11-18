/*
 * The app of MonitorEO for the Earth Engine Code Editor and Earth Engine Apps: the interface over core.js, with the
 * options of the QGIS plugin (region, variable, period, season, comparison, pixel filters, map, time series, trends,
 * burn severity). Instead of a variable of the catalog, the themes of catalog.OTHER_THEMES compute any image or
 * collection of images of Earth Engine given by its ID, or chosen in the GEE Community Catalog. The parameters of each
 * analysis are shown and applied as the JSON of every tool of MonitorEO (monitoreo.parameters). Published as an app,
 * it computes with the Cloud project of the app: whoever uses it needs no account of Earth Engine. LIMITS keep each
 * request within what a shared project can afford.
 */

(function () {
	var mo = MonitorEO;

	var LIMITS = {
		maxAreaKm2: 100000,   // the biggest region (km², all its polygons), except with coarse data (largeM)
		largeM: 250,          // data of pixels of this size (m) or bigger (MODIS, climate) take larger regions, up to
		maxLargeAreaKm2: 1e8, // this (all the oceans of the IHO), computed on pixels of 1 to 10 km (mo.defaultScale)
		s2AreaKm2: 5000,      // Sentinel-2 only for regions up to this size; bigger ones, Landsat or MODIS
		fineM: 20,            // and so the collections given by their ID with pixels of this size (m) or smaller
		maxSteps: 400,        // steps of a time series (and of the series of the trends and comparisons)
		downloadBytes: 32e6   // size of a GeoTIFF (float32): bigger regions are downloaded with bigger pixels
	};

	var T = {
		es: {
			subtitle: 'Mapas, series y tendencias de variables de satélite (Sentinel-2, Landsat y MODIS) sobre ' +
				'áreas protegidas, ecorregiones o tu propia zona. Calcula en Google Earth Engine: no necesitas cuenta.',
			language: 'English', version: 'MonitorEO %s · publicada el %s',
			region: 'Región', mode_wdpa: 'Área protegida (WDPA)', mode_ecoregion: 'Ecorregión', mode_view: 'Vista del mapa',
			mode_admin: 'Unidad administrativa', mode_island: 'Isla', adminHint: 'Nombre, p. ej. Granada',
			level1: 'Nivel 1 (regiones, provincias...)', level2: 'Nivel 2 (provincias, municipios...)',
			level3: 'Nivel 3 (municipios de España, IGN)', adminHint3: 'Nombre o código del INE, p. ej. Monachil',
			level3Help: 'Los municipios de España del Instituto Geográfico Nacional (sus unidades administrativas ' +
				'INSPIRE, CC BY 4.0 ign.es). Busca por el nombre, sin importar mayúsculas ni tildes, o por el código del ' +
				'INE (5 dígitos, p. ej. 18134).',
			countryHint: 'País (ISO3, opcional)', chooseUnit: 'Elige la unidad', noUnit: 'Ninguna unidad con ese nombre.',
			islandHelp: 'Pulsa en el mapa sobre la isla (de más de 1 km²).', ramsar: 'Solo sitios Ramsar',
			mode_sea: 'Mar u océano (IHO)', seaHint: 'Nombre en inglés, p. ej. Alboran', chooseSea: 'Elige el mar',
			noSea: 'Ningún mar con ese nombre: escríbelo en inglés (Alboran, Biscay, Mediterranean...).',
			seaHelp: 'Las áreas marinas de la Organización Hidrográfica Internacional (Marine Regions, CC BY 4.0): ' +
				'búscalas por su nombre en inglés o pulsa en el mapa sobre el mar. Los océanos son lo que queda fuera ' +
				'de sus mares, y el Mediterráneo son varias áreas. Son áreas grandes: píxeles de 1 a 10 km, y solo la ' +
				'clorofila de MODIS (Chl-a) tiene datos en mar abierto.',
			mode_draw: 'Polígono dibujado', search: 'Buscar', searchHint: 'Nombre, p. ej. Sierra Nevada',
			chooseArea: 'Elige el área', none: 'Ninguna área protegida con ese nombre.',
			clickHelp: 'Pulsa en el mapa sobre la ecorregión.', useView: 'Usar la vista del mapa', mode_biome: 'Bioma',
			biomeHelp: 'Pulsa en el mapa sobre el bioma: su parte en la vista del mapa (un bioma entero abarca ' +
				'continentes).', noBiome: 'Ningún bioma en ese punto (¿el mar?).',
			drawHelp: 'Dibuja un polígono en el mapa: un clic por vértice y doble clic para cerrarlo.',
			drawAgain: 'Dibujar otro', regionIs: 'Región: ', noRegion: 'Elige primero una región.',
			mapView: 'Vista del mapa', polygon: 'Polígono dibujado', loadingRegion: 'Cargando la región…',
			theme: 'Tema', allThemes: 'Todas las variables', variable: 'Variable', period: 'Periodo (AAAA-MM-DD)', to: 'a', season: 'Solo esta temporada de cada año (MM-DD)',
			compare: 'Comparar con otro periodo', other: 'Otro periodo',
			filters: 'Quitar píxeles con', clouds: 'nubes y sombras', water: 'agua', snow: 'nieve', aerosols: 'aerosoles',
			landcoverHeader: 'Máscara de usos del suelo', landcoverOn: 'Quitar algunos usos del suelo de los resultados',
			landcoverYear: 'Año del mapa', landcoverLeaveOut: 'Quitar los píxeles de:',
			landcoverNote: 'Un píxel se quita cuando esos usos cubren la mitad o más de él, y donde el mapa no tiene ' +
				'datos (CORINE fuera de Europa). Qué clases de cada mapa son cada uso: manual, Conceptos.',
			noLandcover: 'Máscara de usos del suelo: marca los usos que quitar (o desmarca la máscara).',
			whereHeader: 'Solo los píxeles donde', whereOn: 'una variable está entre dos valores', between: 'entre',
			and: 'y', whereNote: 'Mín. o máx. vacío: sin límite. Una variable con fechas es su media en el periodo, la ' +
			'misma para cada paso y para los dos periodos de una comparación.',
			badLimit: 'El límite %s no es un número.', noLimit: 'Da un mínimo, un máximo o los dos.',
			cloudScore: 'nubes de Sentinel-2 con Cloud Score+ (si no, con la clasificación SCL)',
			conflict: 'Ojo: el filtro de %s quita lo que mide esta variable.',
			fixedFilters: 'Filtros fijos de esta variable: no se pueden cambiar.',
			staticNote: 'Capa fija, sin fechas: solo el mapa y su GeoTIFF. El periodo, las métricas, las series ' +
				'temporales, las tendencias y la comparación de periodos no se aplican.',
			categoricalNote: 'Capa categórica: sus valores son códigos de clases, no cantidades. Su mapa tiene el color de ' +
				'cada clase y la leyenda de las de la región; Superficie por clase da la superficie de cada una; en ' +
				'Gradientes, sus clases son zonas; y «Solo los píxeles donde» guarda o quita algunas. Sin perfiles.',
			whereKeep: 'es una de las clases', whereExclude: 'no es ninguna de las clases', whereCodes: 'códigos, p. ej. 12, 4',
			whereFind: 'buscar una clase por su nombre', whereFound: 'Clases (código y nombre): %s',
			whereClassNote: 'Un píxel se guarda si las clases guardadas cubren la mitad de él o más.',
			noCodes: 'Da los códigos de las clases (búscalos por su nombre).',
			moreClasses: 'y %s clases más', classesShown: '%s clases en la región.',
			areaClassesNote: 'Las clases de la capa categórica elegida como variable (ECOREGION o BIOME, tema Ecosistemas) ' +
				'con superficie en la región; las ecorregiones con su bioma.',
			notCategorical: 'Elige una capa categórica como variable (ECOREGION o BIOME, tema Ecosistemas).',
			zoneClassTitle: '%s por clases de %s', zoneNoCategorical: 'Una capa categórica como variable no tiene ' +
				'percentiles por franjas: su estadística es la clase mayoritaria (en el paquete de Python, region_stats).',
			profileCategorical: 'Una capa categórica (sus valores son códigos de clases) no tiene perfil a lo largo de ' +
				'una línea: usa Superficie por clase.',
			scfNote: 'Frecuencia de nieve: % de las observaciones sin nubes de cada píxel con nieve o hielo. Cada imagen ' +
				'es 100 (nieve) o 0, así que su métrica es siempre la media. Corrige la sombra del relieve con la ' +
				'reflectancia TOA por encima de 1500 m; umbrales fijados en Sierra Nevada.',
			scfModisNote: 'Frecuencia de nieve de MODIS: % de las observaciones sin nubes de cada píxel con nieve o ' +
				'hielo, con su producto diario de nieve (NDSI ≥ 0,35, el umbral de la de Landsat). Cada imagen es 100 ' +
				'(nieve) o 0, así que su métrica es siempre la media.',
			scdNote: 'Días de nieve: en cada píxel, la suma de cada mes de su frecuencia de nieve × sus días (un mes sin ' +
				'imágenes toma la de los demás). Su métrica es siempre «días». Con «Todo el periodo», la media de los ' +
				'días de cada temporada o, sin temporada, de cada 12 meses. Es una estimación: mejor con más imágenes.',
			scdDailyNote: 'Cada barra diaria va de 0 a 1 día: la parte de los píxeles sin nubes con nieve ese día.',
			nImages: 'Imágenes', validPixels: 'Píxeles válidos',
			cfNote: 'Frecuencia de nubes: % de las observaciones de cada píxel con nubes. Cada imagen es 100 (nube) o 0, ' +
				'así que su métrica es siempre la media.',
			map: 'Mapa', metric: 'Métrica', temporal: 'Agregación temporal', t_period: 'Todo el periodo',
			t_annual: 'Cada año y entre años', t_monthly: 'Cada mes y entre años', 't_16-day': 'Cada 16 días y entre años',
			interannual: 'Métrica entre años', addMap: 'Añadir al mapa', download: 'Descargar GeoTIFF',
			animation: 'Animación (timelapse)', animStep: 'Un fotograma por', a_annual: 'Año', a_monthly: 'Mes',
			'a_16-day': '16 días', animMetric: 'Métrica de cada fotograma', makeAnimation: 'Hacer la animación',
			animFrames: '%s fotogramas, con los mismos colores (de %s a %s): %s.',
			animNote: 'Los píxeles sin datos en un fotograma, en gris claro. El GIF con la fecha escrita en cada ' +
				'fotograma, con el paquete de Python, QGIS o el asistente (timelapse).',
			animGif: 'Descargar el GIF', animSlider: 'Fotograma en el mapa',
			doy: 'Una línea por año, sobre los días del año', dayOfYear: 'Día del año',
			doyLines: 'Una línea por año', doyOther: 'Otro índice (eje derecho)', noOther: 'Ninguno',
			ofTheYears: '%s de los años', rightAxis: 'Eje derecho',
			doyNote: 'Cada punto: %s de los valores de ese paso del año en los años del periodo (n_years en el ' +
				'CSV: los años con valor), en la mediana de sus días del año.',
			sameOther: '%s ya es la variable del eje izquierdo: elige otra para el eje derecho.',
			scalesNote: 'Calculado con píxeles de %s m (%s) y de %s m (%s).',
			catalogSearch: 'Buscar en el catálogo de Earth Engine', catalogHint: 'palabras en inglés, p. ej. snow cover',
			catalogFound: '%s conjuntos (colecciones con datos en el periodo, imágenes fijas de cualquier fecha): elige uno',
			catalogNone: 'Ninguno: prueba otras palabras en inglés.',
			swipe: 'Cortina: los dos periodos lado a lado', oneMap: 'Volver a un mapa',
			swipeNote: 'Izquierda: periodo de referencia (%s); derecha: el otro (%s). Los dos mapas se mueven juntos.',
			areas: 'Superficie por clase', areaOf: 'Superficie de cada clase de %s', areaKind: 'Clases de', k_landcover: 'Un mapa de usos del suelo',
			k_breaks: 'La variable, cortada en unos valores', k_trend: 'La tendencia de la variable',
			k_classes: 'Las clases de una capa categórica',
			areaMap: 'Mapa y año', areaBreaks: 'Cortes', breaksHint: 'p. ej. 1500, 2000, 2500',
			computeAreas: 'Calcular las superficies', areaClass: 'Clase', areaPercent: '% de la superficie con clases',
			areaNote: 'Píxeles de %s m. El % es de la superficie con una clase (no cuentan los píxeles sin datos).',
			areaTrendNote: 'Con las opciones de Tendencias (partes del año y métrica de cada año); significativa si p < 0,05.',
			areaChange: 'Sus cambios hasta', areaChanges: 'Cambios de las clases de %s de %s a %s',
			areaChanged: '%s: cambiaron %s ha y no cambiaron %s ha (por clase del mapa).', areaFrom: 'De', areaTo: 'A',
			areaBroad: 'Por usos del suelo generales; cada par de clases, en el CSV.', badYears: 'elige dos años distintos.',
			gradients: 'Gradientes (franjas de altitud y perfiles)', zonesOf: 'Franjas de', zoneStats: 'Estadísticas de cada franja',
			zoneTitle: '%s por franjas de %s', zoneBand: 'Franja', zoneNote: 'Con las opciones de Mapa; píxeles de %s m.',
			drawLine: 'Dibujar una línea y su perfil', drawLineHelp: 'Dibuja la línea en el mapa: un clic por vértice y doble clic para terminarla.',
			profileTitle: '%s a lo largo de una línea de %s km', distance: 'Distancia (km)', elevationM: 'Elevación (m)',
			profileNote: 'Tramos de %s m: la media de los píxeles que cruza cada uno. Con las opciones de Mapa.',
			areaOneYear: '%s tiene un mapa de un solo año: no hay cambios que calcular.',
			areaNoWhere: 'La máscara de usos del suelo y «Solo los píxeles donde» son para las clases de una variable ' +
				'(cortes, tendencia), no para las de un mapa de usos del suelo: desmárcalos.',
			downloadReady: 'GeoTIFF de %s m (NoData -9999): ', downloadLink: 'descargar',
			layer: 'Capa', l_index: 'Índice', l_rgb: 'Color verdadero (RGB)', l_both: 'Ambas',
			rgbNote: 'Color verdadero: la reflectancia roja, verde y azul de las mismas imágenes y píxeles que la ' +
				'variable, con la misma métrica (mínimo y máximo: los colores de la fecha en que la variable es más baja o ' +
				'más alta). Ambas: el índice sobre el color verdadero.',
			rgbStatic: 'Sin color verdadero: una capa fija, sin fechas, no tiene imágenes.',
			rgbNone: 'Sin color verdadero: solo las variables de Sentinel-2 y Landsat y la frecuencia de nubes de MODIS ' +
				'tienen imágenes con bandas roja, verde y azul.',
			rgbCompare: 'Sin color verdadero al comparar dos periodos: el mapa es su diferencia.',
			rgbMetric: 'Sin color verdadero con esta métrica: solo con la media, la mediana, el mínimo, el máximo o un ' +
				'percentil (también entre años).',
			rgbLegend: 'Color verdadero (rojo, verde, azul): reflectancia de %s a %s',
			rgbRangeNote: 'Color verdadero con la reflectancia de 0 a 0,3: Earth Engine no pudo calcular los percentiles ' +
				'2 y 98 de la región.',
			downloadRgb: 'Descargar GeoTIFF del color verdadero (bandas red, green, blue)',
			series: 'Serie temporal', step: 'Paso', s_daily: 'Diario (días con imágenes)', 's_16-day': '16 días',
			s_monthly: 'Mensual', s_annual: 'Anual', stepMetric: 'Métrica de cada paso', stat: 'Estadístico de la región',
			cvAxis: 'Coeficiente de variación',
			computeSeries: 'Calcular la serie temporal',
			trends: 'Tendencias (Mann-Kendall y Sen)', parts: 'Partes del año', p_monthly: 'Meses', 'p_16-day': '16 días',
			p_annual: 'El año', yearMetric: 'Métrica de cada año', trendTable: 'Tabla de tendencias',
			trendPart: 'Parte del año del mapa', output: 'Resultado', o_slope: 'Pendiente de Sen (por año)',
			o_tau: 'τ de Kendall', o_z: 'Z de Mann-Kendall', o_p_value: 'p-valor', o_intercept: 'Valor inicial',
			o_n: 'Años con datos', significant: 'Solo píxeles con tendencia significativa (p < 0,05)',
			trendMap: 'Mapa de tendencia', seeChart: 'Valores de cada año de',
			fire: 'Severidad de un incendio (dNBR, RBR o RdNBR)', sensor: 'Sensor', before: 'Antes del incendio',
			index: 'Índice', idx_dNBR: 'dNBR (clases del USGS)', idx_RBR: 'RBR (continuo, sin clases)',
			idx_RdNBR: 'RdNBR (clases de Miller y Thode 2007)',
			rbrNote: 'RBR = dNBR / (NBR antes + 1,001), con el NBR de B8A y B12 de Sentinel-2 (NIR y SWIR2 de ' +
				'Landsat), sin corrección fenológica y sin multiplicar por 1000.',
			rdnbrHint: 'Para las clases del RdNBR, un periodo después de alrededor de un año tras el incendio, en la ' +
				'misma estación que el periodo antes: las de Miller y Thode 2007 vienen de parcelas de campo medidas un ' +
				'año después del incendio.',
			modisNote: 'MODIS (500 m), solo con el RdNBR: bandas 2 y 7 de su reflectancia de superficie diaria (MOD09GA ' +
				'de Terra, desde 2000-02-24; MYD09GA de Aqua, desde 2002-07-04; Veraverbeke et al. 2010). Las clases ' +
				'del RdNBR vienen de Landsat (30 m), y un píxel de 500 m mezcla suelo quemado y sin quemar, así que su ' +
				'RdNBR es menos extremo, las hectáreas de cada clase son aproximadas y los incendios pequeños se pierden.',
			rdnbrNote: 'RdNBR = dNBR / sqrt(max(|NBR antes|; 0,001)) (Miller y Thode 2007; el 0,001 de Howe et al. ' +
				'2022), con el NBR de B8 y B12 de Sentinel-2 (NIR y SWIR2 de Landsat, bandas 2 y 7 de MODIS), en la ' +
				'escala del dNBR de MonitorEO, sin el factor 1000 del artículo (0,641 aquí es 641 allí) y sin su ' +
				'desplazamiento (el dNBR medio de terreno sin quemar fuera del incendio), como el dNBR y el RBR. Clases ' +
				'de su tabla 4, calibradas con Landsat TM (30 m) y parcelas de campo (índice compuesto de quema) de 14 ' +
				'incendios de Sierra Nevada (California), sobre todo en bosques de coníferas y de encinas (también ' +
				'pino piñonero y artemisa), medidas un año después ' +
				'del incendio, por lo que encajan mejor con un periodo después de alrededor de un año tras el ' +
				'incendio, en la misma estación que el periodo antes; otra vegetación puede necesitar otros umbrales. ' +
				'Sin cambios no es sin quemar: un año después del incendio la zona no se distinguía de antes.',
			after: 'Después del incendio', burn: 'Calcular la severidad',
			burned: 'Superficie quemada (dNBR ≥ 0,1): %s ha', changed: 'Superficie con cambios (RdNBR ≥ 0,069): %s ha',
			severityClasses: 'Clases de severidad', dnbrLegend: 'Severidad del incendio (dNBR, USGS)',
			rdnbrLegend: 'Severidad del incendio (RdNBR, Miller y Thode 2007)', rdnbrBar: 'RdNBR (capa bajo las clases)',
			references: 'Referencias',
			perimeter: 'Perímetro de la superficie quemada',
			perimeterHelp: 'Los polígonos de los píxeles quemados, para descargarlos o usarlos como región de otros ' +
				'análisis (p. ej. el NDVI de los años después del incendio). Quemado desde: vacío, el valor de las ' +
				'clases del índice (dNBR 0,1, RdNBR 0,069); el RBR no tiene clases. Sin los parches de menos de la ' +
				'superficie mínima, y con las islas sin quemar de menos de ella rellenas (0: todos los píxeles).',
			burnedFrom: 'Quemado desde', smallest: 'mínimo', perimeterButton: 'Calcular el perímetro',
			perimeterNumbers: 'Quemado desde y mínimo tienen que ser números (mínimo, 0 o más).',
			perimeterHa: '%s ha en %s parches', noBurned: 'Ningún píxel quemado (%s ≥ %s) en parches del mínimo.',
			perimeterLayer: 'perímetro', useRegion: 'Usar como región', burnedArea: 'Superficie quemada',
			geojson: 'Descargar GeoJSON', kml: 'Descargar KML',
			about: 'Acerca de MonitorEO', manual: 'Manual', repository: 'Código', cite: 'Cómo citar',
			computing: 'Calculando…', progress: 'Calculando… %s de %s pasos', close: 'Cerrar', csv: 'Descargar CSV',
			chartHelp: 'El botón ⤢ de la gráfica la abre en otra pestaña, desde donde se descarga como imagen.',
			scaleNote: 'Calculado con píxeles de %s m.', dataSource: 'Datos:', date: 'Fecha', value: 'Valor', reference: 'Referencia',
			yearAxis: 'Año', senLine: 'recta de Sen', part: 'Parte del año', significantShort: 'signif.',
			yes: 'sí', no: 'no', klass: 'Clase', hectares: 'ha', dnbr: 'dNBR',
			tooBig: 'La región es demasiado grande para esta app (%s km²; máximo %s km²).',
			largeOnly: 'La región tiene %s km²: por encima de %s km², esta app solo calcula datos de píxeles de %s m o ' +
				'más (MODIS, el clima), sobre píxeles de 1 a 10 km.',
			s2TooBig: 'Sentinel-2 solo está disponible para regiones de hasta %s km² (esta tiene %s): elige Landsat o MODIS.',
			fineTooBig: '%s tiene píxeles de %s m: las colecciones de imágenes con píxeles de %s m o menos, como ' +
				'Sentinel-2, solo están disponibles para regiones de hasta %s km² (esta tiene %s).',
			tooManySteps: 'Son %s pasos (máximo %s): usa un paso más largo o un periodo más corto.',
			dailyCompare: 'Para comparar periodos o calcular tendencias, el paso no puede ser diario.',
			fewYears: 'Las tendencias necesitan un periodo de al menos dos años.',
			badDate: 'Fecha no válida: «%s». Usa AAAA-MM-DD (y MM-DD en la temporada).', error: 'Error: ',
			noData: 'No hay datos en ese periodo.',
			rangeNote: 'Colores con el rango del catálogo: Earth Engine no pudo calcular los percentiles 5 y 95 de la región.',
			rangeNoteData: 'Colores de un rango fijo (de 0 a 1; de −0,1 a 0,1 para una diferencia): Earth Engine no pudo ' +
				'calcular los percentiles 5 y 95 de la región.',
			assetId: 'ID de Earth Engine', assetHint: 'p. ej. IDAHO_EPSCOR/TERRACLIMATE', read: 'Leer',
			reading: 'Leyendo el ID en Earth Engine…',
			readFirst: 'Escribe el ID de una imagen o una colección de imágenes de Earth Engine y pulsa Leer.',
			band: 'Banda', useAs: 'Usar como', use_collection: 'Imágenes con fechas (colección)',
			use_image: 'Imagen fija (imagen)', bandScale: 'Escala de la banda', bandOffset: 'Desplazamiento de la banda',
			unit: 'Unidad (UDUNITS)', unitHint: 'p. ej. mm, degC, kg m-2, 1',
			bandNote: 'Valor = valor guardado × escala + desplazamiento, en la unidad dada. Earth Engine no los da: ' +
				'búscalos en la página del conjunto de datos.',
			combine: 'Combinar bandas', combine_one: 'Una banda', combine_sum: 'Suma de las bandas',
			combine_mean: 'Media de las bandas', bands: 'Bandas',
			combineNote: 'Cada banda × escala + desplazamiento; después, en cada píxel con datos en todas ellas, su suma ' +
				'o su media, en la unidad de las bandas (12 bandas mensuales en mm suman mm), sobre los píxeles de la ' +
				'primera.',
			combineTwo: 'Marca dos o más bandas para combinarlas (o elige Una banda).',
			combineScales: 'Las bandas marcadas tienen píxeles de distinto tamaño: se combinan sobre los de la primera ' +
				'(%s m).',
			customFilters: 'Estos datos guardan su propia máscara: los filtros de píxeles de MonitorEO son para las ' +
				'variables de su catálogo.',
			datasetPage: 'Página del conjunto de datos', src_data: 'Catálogo de datos de Earth Engine',
			src_community: 'Catálogo de la comunidad de GEE', src_asset: 'Asset de Earth Engine', licence: 'Licencia',
			licenceInPage: 'licencia en su página', type_image: 'imagen', type_image_collection: 'colección',
			communityTheme: 'Tema del catálogo', dataset: 'Conjunto de datos', chooseDataset: 'Elige el conjunto de datos',
			communityNote: 'Copia del índice del Catálogo de la comunidad de GEE (gee-community-catalog.org, CC BY 4.0) ' +
				'del %s.',
			badNumber: '%s: «%s» no es un número.',
			params: 'Parámetros del análisis (JSON)', paramsAnalysis: 'Análisis', paramsShow: 'Mostrar los parámetros',
			paramsApply: 'Aplicar los parámetros', paramsHint: 'Pega aquí los parámetros de un análisis (JSON)',
			paramsHelp: 'Los parámetros de un análisis en JSON, los mismos en todas las herramientas de MonitorEO ' +
				'(paquetes de Python y R, línea de comandos, QGIS, asistente), para repetirlo o llevarlo a otra: Mostrar ' +
				'escribe en la caja los del análisis elegido (el último calculado), para copiarlos (Ctrl+A, Ctrl+C); ' +
				'Aplicar pone el panel con los pegados en ella, sin calcular, y dice cuáles no se aplican y por qué. ' +
				'Manual: App de Earth Engine.',
			paramsShown: 'Parámetros de %s: selecciona el texto de la caja y cópialo.',
			paramsSet: '%s (%s): pulsa «%s» para calcularlo.', paramsAlias: '%s se calcula en la app como %s.',
			paramsNotApplied: 'No aplicados:',
			paramsVersion: 'Guardados con MonitorEO %s, aplicados en la app de %s: los parámetros que cambiaron entre ' +
				'ellas están en No aplicados.',
			paramsNoRegion: 'Sin región: elige una.', paramsNoLine: 'Sin línea: dibújala (Gradientes).',
			paramsOtherFirst: 'Eje derecho: %s de %s; las demás herramientas toman la primera colección de su variable y ' +
				'sensor, %s.',
			paramsOtherFilter: 'Eje derecho: la app calcula %s sin el filtro de %s; las demás herramientas, con los mismos ' +
				'filtros de píxeles en los dos ejes, con él.',
			notParameter: 'no es un parámetro de %s en la app de Earth Engine',
			anOutput: 'una salida: cada herramienta escribe sus propios archivos',
			noAnalysis: 'la app de Earth Engine no tiene %s: calcúlalo con el paquete de Python, la línea de comandos o QGIS',
			notOption: 'no es una opción de la app: %s', noWidget: 'la app no tiene esa opción',
			regionFile: 'un archivo del ordenador: la app no lee archivos; dibuja el polígono o da su GeoJSON (geojson)',
			regionKind: 'una región que la app no usa: toma wdpa_id, admin1, admin2, admin3, sea, sea_at, ecoregion_at, ' +
				'island_at, bbox, geojson y biome_at dentro de un bbox (within)',
			regionOne: 'la app toma una sola unidad administrativa',
			lineDrawn: 'la app toma la línea dibujada en el mapa (Gradientes: Dibujar una línea y su perfil)',
			whereOne: 'la app toma una condición sobre una variable y una de usos del suelo',
			whereOwn: 'la app calcula la condición con la media en el periodo del análisis',
			onlyAlpha: 'la app toma como significativas las tendencias con p < 0,05',
			noZones: 'la app calcula region_stats por zonas (Gradientes): las franjas de una capa fija o las clases de una ' +
				'categórica',
			zonesFixed: 'las zonas de la app son una capa fija cortada en unos valores (ELEVATION, SLOPE, TWI...) o las ' +
				'clases de una capa categórica',
			inResults: 'se da en los resultados de la severidad (Perímetro de la superficie quemada)',
			twoPeriods: '%s compara dos periodos: burn_severity (Severidad de un incendio)',
			withDates: 'el eje derecho es una variable del catálogo con fechas',
			noSource: 'sin variable ni ID de los datos'
		},
		en: {
			subtitle: 'Maps, time series and trends of satellite variables (Sentinel-2, Landsat and MODIS) over ' +
				'protected areas, ecoregions or your own area. Computed in Google Earth Engine: no account needed.',
			language: 'Español', version: 'MonitorEO %s · released %s',
			region: 'Region', mode_wdpa: 'Protected area (WDPA)', mode_ecoregion: 'Ecoregion', mode_view: 'Map view',
			mode_admin: 'Administrative unit', mode_island: 'Island', adminHint: 'Name, e.g. Granada',
			level1: 'Level 1 (regions, provinces...)', level2: 'Level 2 (provinces, municipalities...)',
			level3: 'Level 3 (municipalities of Spain, IGN)', adminHint3: 'Name or INE code, e.g. Monachil',
			level3Help: 'The municipalities of Spain of the Instituto Geográfico Nacional (its INSPIRE administrative ' +
				'units, CC BY 4.0 ign.es). Search by name, whatever the case and accents, or by the code of the INE (5 ' +
				'digits, e.g. 18134).',
			countryHint: 'Country (ISO3, optional)', chooseUnit: 'Choose the unit', noUnit: 'No unit with that name.',
			islandHelp: 'Click on the map over the island (of more than 1 km²).', ramsar: 'Ramsar sites only',
			mode_sea: 'Sea or ocean (IHO)', seaHint: 'Name in English, e.g. Alboran', chooseSea: 'Choose the sea',
			noSea: 'No sea with that name: write it in English (Alboran, Biscay, Mediterranean...).',
			seaHelp: 'The sea areas of the International Hydrographic Organization (Marine Regions, CC BY 4.0): search ' +
				'them by their English name or click on the map over the sea. The oceans are what is left out of their ' +
				'seas, and the Mediterranean is several areas. They are large areas: pixels of 1 to 10 km, and only the ' +
				'chlorophyll of MODIS (Chl-a) has data over the open sea.',
			mode_draw: 'Drawn polygon', search: 'Search', searchHint: 'Name, e.g. Sierra Nevada',
			chooseArea: 'Choose the area', none: 'No protected area with that name.',
			clickHelp: 'Click on the map over the ecoregion.', useView: 'Use the map view', mode_biome: 'Biome',
			biomeHelp: 'Click on the map over the biome: its part in the map view (a whole biome spans continents).',
			noBiome: 'No biome at that point (the sea?).',
			drawHelp: 'Draw a polygon on the map: a click per vertex and a double click to close it.',
			drawAgain: 'Draw another', regionIs: 'Region: ', noRegion: 'Choose a region first.',
			mapView: 'Map view', polygon: 'Drawn polygon', loadingRegion: 'Loading the region…',
			theme: 'Theme', allThemes: 'All the variables', variable: 'Variable', period: 'Period (YYYY-MM-DD)', to: 'to', season: 'Only this season of each year (MM-DD)',
			compare: 'Compare with another period', other: 'Other period',
			filters: 'Remove pixels with', clouds: 'clouds and shadows', water: 'water', snow: 'snow', aerosols: 'aerosols',
			landcoverHeader: 'Land cover mask', landcoverOn: 'Leave some land covers out of the results',
			landcoverYear: 'Year of the map', landcoverLeaveOut: 'Leave out the pixels of:',
			landcoverNote: 'A pixel is left out when those land covers cover half of it or more, and where the map has ' +
				'no data (CORINE outside Europe). Which classes of each map are each land cover: manual, Concepts.',
			noLandcover: 'Land cover mask: check the land covers to leave out (or uncheck the mask).',
			whereHeader: 'Only the pixels where', whereOn: 'a variable is between two values', between: 'between',
			and: 'and', whereNote: 'An empty min or max: no limit. A variable with dates is its mean over the period, the ' +
			'same for every step and for both periods of a comparison.',
			badLimit: 'The limit %s is not a number.', noLimit: 'Give a min, a max or both.',
			cloudScore: 'Sentinel-2 clouds with Cloud Score+ (otherwise, with the SCL classification)',
			conflict: 'Note: the %s filter removes what this variable measures.',
			fixedFilters: 'Fixed filters of this variable: they cannot be changed.',
			staticNote: 'Fixed layer, without dates: only the map and its GeoTIFF. The period, metrics, time series, ' +
				'trends and comparison of periods do not apply.',
			categoricalNote: 'Categorical layer: its values are class codes, not quantities. Its map has the colour of ' +
				'each class and the legend of those in the region; Area by class gives the area of each one; in ' +
				'Gradients, its classes are zones; and «Only the pixels where» keeps or leaves out some. No profiles.',
			whereKeep: 'is one of the classes', whereExclude: 'is none of the classes', whereCodes: 'codes, e.g. 12, 4',
			whereFind: 'find a class by its name', whereFound: 'Classes (code and name): %s',
			whereClassNote: 'A pixel is kept when the classes kept cover half of it or more.',
			noCodes: 'Give the codes of the classes (find them by their name).',
			moreClasses: 'and %s more classes', classesShown: '%s classes in the region.',
			areaClassesNote: 'The classes of the categorical layer chosen as the variable (ECOREGION or BIOME, theme ' +
				'Ecosystems) with area in the region; the ecoregions with their biome.',
			notCategorical: 'Choose a categorical layer as the variable (ECOREGION or BIOME, theme Ecosystems).',
			zoneClassTitle: '%s by classes of %s', zoneNoCategorical: 'A categorical layer as the variable has no ' +
				'percentiles by zones: its statistic is the majority class (in the Python package, region_stats).',
			profileCategorical: 'A categorical layer (its values are class codes) has no profile along a line: use Area ' +
				'by class.',
			scfNote: 'Snow cover frequency: % of the clear observations of each pixel with snow or ice. Each image is ' +
				'100 (snow) or 0, so its metric is always the mean. It corrects the shadow of the relief with the TOA ' +
				'reflectance above 1500 m; thresholds set in Sierra Nevada.',
			scfModisNote: 'Snow cover frequency of MODIS: % of the clear observations of each pixel with snow or ice, ' +
				'from its daily snow product (NDSI ≥ 0.35, the threshold of that of Landsat). Each image is 100 (snow) ' +
				'or 0, so its metric is always the mean.',
			scdNote: 'Snow cover days: on each pixel, the sum over the months of its snow cover frequency × their days ' +
				'(a month without images takes that of the others). Its metric is always days. With Whole period, the ' +
				'mean days of each season or, without a season, of each 12 months. An estimate: better with more images.',
			scdDailyNote: 'Each daily bar goes from 0 to 1 day: the share of the clear pixels with snow that day.',
			nImages: 'Images', validPixels: 'Valid pixels',
			cfNote: 'Cloud frequency: % of the observations of each pixel with clouds. Each image is 100 (cloud) or 0, ' +
				'so its metric is always the mean.',
			map: 'Map', metric: 'Metric', temporal: 'Temporal aggregation', t_period: 'Whole period',
			t_annual: 'Each year, then between years', t_monthly: 'Each month, then between years',
			't_16-day': 'Each 16 days, then between years', interannual: 'Metric between years', addMap: 'Add to the map',
			animation: 'Animation (timelapse)', animStep: 'A frame per', a_annual: 'Year', a_monthly: 'Month',
			'a_16-day': '16 days', animMetric: 'Metric of each frame', makeAnimation: 'Make the animation',
			animFrames: '%s frames, with the same colours (from %s to %s): %s.',
			animNote: 'The pixels without data in a frame, in light grey. The GIF with the date written on each frame, ' +
				'with the Python package, QGIS or the assistant (timelapse).',
			animGif: 'Download the GIF', animSlider: 'Frame on the map',
			doy: 'A line per year, over the days of the year', dayOfYear: 'Day of the year',
			doyLines: 'A line per year', doyOther: 'Other index (right axis)', noOther: 'None',
			ofTheYears: '%s of the years', rightAxis: 'Right axis',
			doyNote: 'Each point: %s of the values of that step of the year in the years of the period (n_years in ' +
				'the CSV: the years with a value), at the median of their days of the year.',
			sameOther: '%s is already the variable of the left axis: choose another one for the right axis.',
			scalesNote: 'Computed on pixels of %s m (%s) and of %s m (%s).',
			catalogSearch: 'Search the Earth Engine data catalog', catalogHint: 'words in English, e.g. snow cover',
			catalogFound: '%s datasets (collections with data in the period, fixed images of any date): choose one',
			catalogNone: 'None: try other words in English.',
			swipe: 'Swipe: the two periods side by side', oneMap: 'Back to one map',
			swipeNote: 'Left: reference period (%s); right: the other one (%s). Both maps move together.',
			areas: 'Area by class', areaOf: 'Area of each class of %s', areaKind: 'Classes of', k_landcover: 'A land cover map',
			k_breaks: 'The variable, cut at some values', k_trend: 'The trend of the variable',
			k_classes: 'The classes of a categorical layer',
			areaMap: 'Map and year', areaBreaks: 'Breaks', breaksHint: 'e.g. 1500, 2000, 2500',
			computeAreas: 'Compute the areas', areaClass: 'Class', areaPercent: '% of the area with classes',
			areaNote: 'Pixels of %s m. The % is of the area with a class (the pixels without data are not counted).',
			areaTrendNote: 'With the options of Trends (parts of the year and metric of each year); significant if p < 0.05.',
			areaChange: 'Its changes to', areaChanges: 'Changes of the classes of %s from %s to %s',
			areaChanged: '%s: %s ha changed and %s ha did not (by class of the map).', areaFrom: 'From', areaTo: 'To',
			areaBroad: 'By broad land cover; each pair of classes, in the CSV.', badYears: 'choose two different years.',
			gradients: 'Gradients (elevation bands and profiles)', zonesOf: 'Bands of', zoneStats: 'Statistics of each band',
			zoneTitle: '%s by bands of %s', zoneBand: 'Band', zoneNote: 'With the options of Map; pixels of %s m.',
			drawLine: 'Draw a line and its profile', drawLineHelp: 'Draw the line on the map: a click per vertex and a double click to end it.',
			profileTitle: '%s along a line of %s km', distance: 'Distance (km)', elevationM: 'Elevation (m)',
			profileNote: 'Segments of %s m: the mean of the pixels that each one crosses. With the options of Map.',
			areaOneYear: '%s has a map of a single year: there are no changes to compute.',
			areaNoWhere: 'The land cover mask and «Only the pixels where» are for the classes of a variable (breaks, ' +
				'trend), not for those of a land cover map: uncheck them.',
			download: 'Download GeoTIFF', downloadReady: 'GeoTIFF of %s m (NoData -9999): ', downloadLink: 'download',
			layer: 'Layer', l_index: 'Index', l_rgb: 'True colour (RGB)', l_both: 'Both',
			rgbNote: 'True colour: the red, green and blue reflectance of the same images and pixels as the variable, ' +
				'with the same metric (minimum and maximum: the colours of the date when the variable is lowest or ' +
				'highest). Both: the index on top of the true colour.',
			rgbStatic: 'No true colour: a fixed layer, without dates, has no images.',
			rgbNone: 'No true colour: only the variables of Sentinel-2 and Landsat and the cloud frequency of MODIS have ' +
				'images with red, green and blue bands.',
			rgbCompare: 'No true colour when comparing two periods: the map is their difference.',
			rgbMetric: 'No true colour with this metric: only with the mean, median, minimum, maximum or a percentile ' +
				'(also between years).',
			rgbLegend: 'True colour (red, green, blue): reflectance from %s to %s',
			rgbRangeNote: 'True colour with the reflectance from 0 to 0.3: Earth Engine could not compute the ' +
				'percentiles 2 and 98 of the region.',
			downloadRgb: 'Download GeoTIFF of the true colour (bands red, green, blue)',
			series: 'Time series', step: 'Step', s_daily: 'Daily (days with images)', 's_16-day': '16 days',
			s_monthly: 'Monthly', s_annual: 'Annual', stepMetric: 'Metric of each step', stat: 'Statistic of the region',
			cvAxis: 'Coefficient of variation',
			computeSeries: 'Compute the time series',
			trends: 'Trends (Mann-Kendall and Sen)', parts: 'Parts of the year', p_monthly: 'Months', 'p_16-day': '16 days',
			p_annual: 'The year', yearMetric: 'Metric of each year', trendTable: 'Trend table',
			trendPart: 'Part of the year of the map', output: 'Output', o_slope: 'Sen\'s slope (per year)',
			o_tau: 'Kendall\'s τ', o_z: 'Mann-Kendall Z', o_p_value: 'p-value', o_intercept: 'Initial value',
			o_n: 'Years with data', significant: 'Only pixels with a significant trend (p < 0.05)',
			trendMap: 'Trend map', seeChart: 'Values of each year of',
			fire: 'Burn severity of a fire (dNBR, RBR or RdNBR)', sensor: 'Sensor', before: 'Before the fire',
			after: 'After the fire',
			index: 'Index', idx_dNBR: 'dNBR (USGS classes)', idx_RBR: 'RBR (continuous, no classes)',
			idx_RdNBR: 'RdNBR (Miller & Thode 2007 classes)',
			rbrNote: 'RBR = dNBR / (NBR before + 1.001), with the NBR of B8A and B12 of Sentinel-2 (NIR and SWIR2 of ' +
				'Landsat), without phenological correction and without the factor 1000.',
			rdnbrHint: 'For the classes of the RdNBR, a period after about one year after the fire, in the same season ' +
				'as the period before it: those of Miller & Thode 2007 come from field plots measured one year after ' +
				'the fire.',
			modisNote: 'MODIS (500 m), only with the RdNBR: bands 2 and 7 of its daily surface reflectance (MOD09GA of ' +
				'Terra, since 2000-02-24; MYD09GA of Aqua, since 2002-07-04; Veraverbeke et al. 2010). The classes of ' +
				'the RdNBR come from Landsat (30 m), and a pixel of 500 m mixes burned and unburned land, so its RdNBR ' +
				'is less extreme, the hectares of each class are approximate and small fires are missed.',
			rdnbrNote: 'RdNBR = dNBR / sqrt(max(|NBR before|, 0.001)) (Miller & Thode 2007; the 0.001 of Howe et al. ' +
				'2022), with the NBR of B8 and B12 of Sentinel-2 (NIR and SWIR2 of Landsat, bands 2 and 7 of MODIS), on ' +
				'the scale of the dNBR of MonitorEO, without the factor 1000 of the article (0.641 here is 641 there) ' +
				'and without its offset (the mean dNBR of unburned land outside the fire), as the dNBR and the RBR. ' +
				'Classes of its Table 4, calibrated with Landsat TM (30 m) and field plots (composite burn index) of 14 ' +
				'fires of the Sierra Nevada of California, mostly in conifer and live oak forests (also pinyon pine and ' +
				'sagebrush), measured one year after the fire, ' +
				'so they fit best a period after about one year after the fire, in the same season as the period ' +
				'before; other vegetation may need other thresholds. Unchanged is not unburned: one year after the ' +
				'fire the area could not be told from before it.',
			burn: 'Compute the severity', burned: 'Burned area (dNBR ≥ 0.1): %s ha',
			changed: 'Changed area (RdNBR ≥ 0.069): %s ha', severityClasses: 'Severity classes',
			dnbrLegend: 'Burn severity (dNBR, USGS)', rdnbrLegend: 'Burn severity (RdNBR, Miller & Thode 2007)',
			rdnbrBar: 'RdNBR (layer under the classes)', references: 'References',
			perimeter: 'Perimeter of the burned area',
			perimeterHelp: 'The polygons of the burned pixels, to download them or to use them as the region of other ' +
				'analyses (e.g. the NDVI of the years after the fire). Burned from: empty, the value of the classes of ' +
				'the index (dNBR 0.1, RdNBR 0.069); the RBR has no classes. Without the patches of less than the ' +
				'smallest area, and with the unburned islands of less than it filled (0: every pixel).',
			burnedFrom: 'Burned from', smallest: 'smallest', perimeterButton: 'Compute the perimeter',
			perimeterNumbers: 'Burned from and smallest have to be numbers (smallest, 0 or more).',
			perimeterHa: '%s ha in %s patches', noBurned: 'No burned pixel (%s ≥ %s) in patches of the smallest area.',
			perimeterLayer: 'perimeter', useRegion: 'Use as the region', burnedArea: 'Burned area',
			geojson: 'Download GeoJSON', kml: 'Download KML',
			about: 'About MonitorEO', manual: 'Manual', repository: 'Code', cite: 'How to cite',
			computing: 'Computing…', progress: 'Computing… %s of %s steps', close: 'Close', csv: 'Download CSV',
			chartHelp: 'The ⤢ button of the chart opens it in another tab, where it can be downloaded as an image.',
			scaleNote: 'Computed on pixels of %s m.', dataSource: 'Data:', date: 'Date', value: 'Value', reference: 'Reference',
			yearAxis: 'Year', senLine: 'Sen line', part: 'Part of the year', significantShort: 'signif.',
			yes: 'yes', no: 'no', klass: 'Class', hectares: 'ha', dnbr: 'dNBR',
			tooBig: 'The region is too big for this app (%s km²; at most %s km²).',
			largeOnly: 'The region has %s km²: above %s km², this app only computes data of pixels of %s m or more ' +
				'(MODIS, the climate), on pixels of 1 to 10 km.',
			s2TooBig: 'Sentinel-2 is only available for regions up to %s km² (this one has %s): choose Landsat or MODIS.',
			fineTooBig: '%s has pixels of %s m: collections of images with pixels of %s m or less, like Sentinel-2, are ' +
				'only available for regions up to %s km² (this one has %s).',
			tooManySteps: '%s steps (at most %s): use a longer step or a shorter period.',
			dailyCompare: 'To compare periods or compute trends, the step cannot be daily.',
			fewYears: 'Trends need a period of at least two years.',
			badDate: 'Not a valid date: "%s". Use YYYY-MM-DD (and MM-DD for the season).', error: 'Error: ',
			noData: 'No data in that period.',
			rangeNote: 'Colours with the range of the catalog: Earth Engine could not compute the percentiles 5 and 95 of the region.',
			rangeNoteData: 'Colours of a fixed range (0 to 1; −0.1 to 0.1 for a difference): Earth Engine could not ' +
				'compute the percentiles 5 and 95 of the region.',
			assetId: 'Earth Engine ID', assetHint: 'e.g. IDAHO_EPSCOR/TERRACLIMATE', read: 'Read',
			reading: 'Reading the ID in Earth Engine…',
			readFirst: 'Write the ID of an image or a collection of images of Earth Engine and press Read.',
			band: 'Band', useAs: 'Use as', use_collection: 'Images with dates (collection)',
			use_image: 'Fixed image (image)', bandScale: 'Band scale', bandOffset: 'Band offset',
			unit: 'Unit (UDUNITS)', unitHint: 'e.g. mm, degC, kg m-2, 1',
			bandNote: 'Value = stored value × scale + offset, in the unit given. Earth Engine does not give them: read ' +
				'them in the page of the dataset.',
			combine: 'Combine bands', combine_one: 'One band', combine_sum: 'Sum of the bands',
			combine_mean: 'Mean of the bands', bands: 'Bands',
			combineNote: 'Each band × scale + offset; then, on each pixel with data in all of them, their sum or their ' +
				'mean, in the unit of the bands (12 monthly bands in mm sum to mm), on the pixels of the first.',
			combineTwo: 'Check two or more bands to combine them (or choose One band).',
			combineScales: 'The bands checked have pixels of different sizes: they are combined on those of the first ' +
				'(%s m).',
			customFilters: 'These data keep their own mask: the pixel filters of MonitorEO are for the variables of its ' +
				'catalog.',
			datasetPage: 'Page of the dataset', src_data: 'Earth Engine data catalog',
			src_community: 'GEE Community Catalog', src_asset: 'Earth Engine asset', licence: 'Licence',
			licenceInPage: 'licence in its page', type_image: 'image', type_image_collection: 'collection',
			communityTheme: 'Theme of the catalog', dataset: 'Dataset', chooseDataset: 'Choose the dataset',
			communityNote: 'Copy of the index of the GEE Community Catalog (gee-community-catalog.org, CC BY 4.0) of %s.',
			badNumber: '%s: "%s" is not a number.',
			params: 'Parameters of the analysis (JSON)', paramsAnalysis: 'Analysis', paramsShow: 'Show the parameters',
			paramsApply: 'Apply parameters', paramsHint: 'Paste here the parameters of an analysis (JSON)',
			paramsHelp: 'The parameters of an analysis as JSON, the same in every tool of MonitorEO (Python and R ' +
				'packages, command line, QGIS, assistant), to repeat it or take it to another one: Show writes in the box ' +
				'those of the analysis chosen (the last one computed), to copy them (Ctrl+A, Ctrl+C); Apply sets the panel ' +
				'from those pasted in it, without computing, and says which ones are not applied and why. Manual: Earth ' +
				'Engine app.',
			paramsShown: 'Parameters of %s: select the text of the box and copy it.',
			paramsSet: '%s (%s): press «%s» to compute it.', paramsAlias: '%s is computed in the app as %s.',
			paramsNotApplied: 'Not applied:',
			paramsVersion: 'Saved with MonitorEO %s, applied in the app of %s: the parameters that changed between them ' +
				'are in Not applied.',
			paramsNoRegion: 'Without region: choose one.', paramsNoLine: 'Without line: draw it (Gradients).',
			paramsOtherFirst: 'Right axis: %s of %s; the other tools take the first collection of its variable and sensor, ' +
				'%s.',
			paramsOtherFilter: 'Right axis: the app computes %s without the %s filter; the other tools, with the same pixel ' +
				'filters on both axes, with it.',
			notParameter: 'not a parameter of %s in the Earth Engine app',
			anOutput: 'an output: each tool writes its own files',
			noAnalysis: 'the Earth Engine app does not have %s: compute it with the Python package, the command line or QGIS',
			notOption: 'not an option of the app: %s', noWidget: 'the app has no option for it',
			regionFile: 'a file of the computer: the app reads no files; draw the polygon, or give its GeoJSON (geojson)',
			regionKind: 'a region the app cannot use: it takes wdpa_id, admin1, admin2, admin3, sea, sea_at, ecoregion_at, ' +
				'island_at, bbox, geojson and biome_at within a bbox (within)',
			regionOne: 'the app takes one administrative unit',
			lineDrawn: 'the app takes the line drawn on the map (Gradients: Draw a line and its profile)',
			whereOne: 'the app takes one condition on a variable and one of land cover',
			whereOwn: 'the app computes the condition with its mean over the period of the analysis',
			onlyAlpha: 'the app takes as significant the trends with p < 0.05',
			noZones: 'the app computes region_stats by zones (Gradients): the bands of a fixed layer or the classes of a ' +
				'categorical one',
			zonesFixed: 'the zones of the app are a fixed layer cut at some values (ELEVATION, SLOPE, TWI...) or the ' +
				'classes of a categorical layer',
			inResults: 'given in the results of the severity (Perimeter of the burned area)',
			twoPeriods: '%s compares two periods: burn_severity (Burn severity of a fire)',
			withDates: 'the right axis is a variable of the catalog with dates',
			noSource: 'without a variable or the ID of the data'
		}
	};

	var METRICS = ['mean', 'median', 'min', 'max', 'p5', 'p10', 'p25', 'p75', 'p90', 'p95', 'std', 'cv', 'count'];
	var STATS = ['mean', 'median', 'min', 'max', 'std', 'cv', 'p5', 'p10', 'p25', 'p75', 'p90', 'p95'];
	var METRIC_NAMES = {
		es: {mean: 'Media', median: 'Mediana', min: 'Mínimo', max: 'Máximo', std: 'Desviación típica',
			cv: 'Coeficiente de variación (%)', count: 'Número', sum: 'Suma', days: 'Días (de nieve)'},
		en: {mean: 'Mean', median: 'Median', min: 'Minimum', max: 'Maximum', std: 'Standard deviation',
			cv: 'Coefficient of variation (%)', count: 'Count', sum: 'Sum', days: 'Days (snow cover)'}
	};

	var state = {
		lang: 'en', mode: 'wdpa', wdpaText: 'Sierra Nevada', wdpaItems: null, wdpaNames: {}, wdpaId: null, ramsar: false,
		adminText: '', adminLevel: 1, adminCountry: '', adminItems: null, adminNames: {}, adminCode: null,
		seaText: '', seaItems: null, seaNames: {}, seaId: null,  // the oceans and seas (mode sea)
		region: null, regionName: null, info: null,
		regionAdmin: null,  // the level of the administrative unit that is the region, or 'sea' (its credits), or null
		feedbackOpen: false, theme: 'vegetation', ref: 27, period: ['2025-01-01', '2025-12-31'], seasonOn: false, season: ['06-01', '08-31'],
		compareOn: false, other: ['2020-01-01', '2020-12-31'],
		quality: {clouds: true, water: true, snow: true, aerosols: true, cloud_score: 0.6},
		// the filters chosen by the user while a variable with fixed filters (SCF, CF, data by ID) is selected: those of
		// the variable of the right axis of a profile (otherQuality), as chosen_filters of the QGIS plugin
		chosenQuality: null,
		whereOn: false, whereRef: null, whereMin: '1500', whereMax: '',  // where: one condition (default: ELEVATION)
		// on a categorical layer (ECOREGION, BIOME): its classes to keep ('classes') or to leave out ('exclude'), by
		// their codes, and the text of the search of a class by its name
		whereKeep: 'classes', whereCodes: '', whereFind: '',
		// the land cover mask, a condition of where: its map, year (null: the default of the map) and land covers left out
		landcoverOn: false, landcoverMap: 'WorldCover', landcoverYear: null, landcoverExclude: ['water', 'built'],
		mapMetric: 'median', temporal: 'period', interannual: 'mean', mapLayer: 'index',  // index, rgb or both
		step: 'monthly', stepMetric: 'mean', stat: 'mean',
		trendStep: 'monthly', trendMetric: 'mean', trendPart: 7, output: 'slope', significant: false,
		animStep: 'annual', animMetric: 'median', doy: false,  // doy: the series with a line per year
		// or, by day of the year, its seasonal profile: the metric between the years ('years': a line per year) and the
		// variable of the right axis ('none', or its ref)
		doyBetween: 'years', doyOther: 'none',
		areaKind: 'landcover', areaMap: 'WorldCover', areaYear: null, areaBreaks: '',  // area by class
		areaChangeOn: false, areaOther: null,  // the changes of the land cover map to another year
		zoneRef: null, zoneBreaks: '1500, 2000, 2500, 3000', drawingLine: false,  // gradients: the bands and the line
		fireSensor: 'Sentinel-2', fireBefore: ['2025-06-01', '2025-07-31'], fireAfter: ['2025-09-01', '2025-10-31'],
		fireIndex: 'dNBR',
		// the data of Earth Engine of the themes of catalog.OTHER_THEMES: the ID written and the one read (mo.assetInfo),
		// its band, or how several are combined (combine: 'one', 'sum' or 'mean', the band_reducer of the package) and
		// those checked (chosen), use (collection or image), scale, offset and unit as written, why the last ID could
		// not be read (error), and the theme and dataset of the GEE Community Catalog chosen
		catalogText: '', catalogFound: null,  // the search of the Earth Engine data catalog (theme earth_engine)
		data: {text: '', reading: null, asset: null, type: null, dated: false, use: 'collection', bands: [], scales: {},
			band: null, combine: 'one', chosen: [], scale: '', offset: '', unit: '', title: null, source: null,
			page: null, licence: null, error: null, communityTheme: null, communityId: null},
		// the parameters of the analysis as JSON (monitoreo.parameters): the analysis (the function of monitoreo.services
		// of the last one computed, or the one chosen), the region as areas.region takes it (regionSpec) and the line of the
		// last profile (a GeoJSON LineString), the text of the box and what Show or Apply said (paramsReport)
		analysis: 'map_layer', regionSpec: null, line: null, paramsText: '', paramsReport: null
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
	// the warnings of the period of a result (days without images of its data: mo.checkPeriod), over it
	var WARNING = {fontSize: '12px', color: '#b35900', whiteSpace: 'pre-wrap'};

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

	// The map of the app again in place of the two maps of a swipe (swipePeriods), so that nothing is drawn on a map
	// that is not shown
	var swiped = false;
	function oneMap() {
		if (!swiped) return;
		ui.root.widgets().set(1, map);
		swiped = false;
	}

	// Results: a panel to the right of the map, with the answer of the last computation (and the map of the app, if a
	// swipe was shown): unless BARE (a message: computing, an error...), over it the warnings of its period (the days
	// without images of its data, see mo.checkPeriod) and under it the data its values come from («Data: ...», as the
	// charts of the package), those of the computation that is running (runNotes: a click that fails before it
	// starts, or a newer one, does not change them)
	var runNotes = mo.notes();
	function show(widgets, bare) {
		oneMap();
		results.clear();
		results.add(row(ui.Label('MonitorEO', {fontWeight: 'bold', fontSize: '16px', stretch: 'horizontal'}),
			button(t('close'), function () {
				oneMap();
				results.style().set('shown', false);
			})));
		var notes = runNotes;
		if (!bare && notes.warnings.length) results.add(ui.Label('⚠ ' + notes.warnings.join('\n⚠ '), WARNING));
		widgets.forEach(function (w) { results.add(w); });
		var source = bare ? null : mo.sourceText(notes);
		if (source) results.add(ui.Label(t('dataSource') + ' ' + source, SMALL));
		results.style().set('shown', true);
	}

	function message(text, error) {
		show([ui.Label(text, {color: error ? '#b00020' : '#333', whiteSpace: 'pre-wrap'})], true);
	}

	function fail(error) {
		message(t('error') + error, true);
	}

	// No data in that period: an answer, with the warnings of its period that explain it (e.g. it begins after the last
	// image of data that ended) and its data, not a bare message
	function noData() {
		show([ui.Label(t('noData'), {color: '#b00020', whiteSpace: 'pre-wrap'})]);
	}

	function start() {
		run += 1;
		runNotes = mo.notes();  // those of the specs of this computation (guarded made them new): shown with its answer
		message(t('computing'));
		return run;
	}

	function colourBar(vis, title) {
		legend.clear();
		addColourBar(vis, title);
	}

	// The colour bar of VIS with its TITLE at the end of the legend, or of PANEL (MARGIN: that of the title; below the
	// classes of the RdNBR, that of its continuous layer)
	function addColourBar(vis, title, margin, panel) {
		panel = panel || legend;
		panel.add(ui.Label(title, {fontWeight: 'bold', fontSize: '12px', margin: margin || '0 0 4px 0'}));
		panel.add(ui.Thumbnail({image: ee.Image.pixelLonLat().select(0), params: {bbox: [0, 0, 1, 0.1],
			dimensions: '200x12', format: 'png', min: 0, max: 1, palette: vis.palette}, style: {margin: '0'}}));
		panel.add(row(ui.Label(num(vis.min), {fontSize: '11px', margin: '0'}),
			ui.Label(num(vis.max), {fontSize: '11px', margin: '0 0 0 150px'})));
		panel.style().set('shown', true);
	}

	// The range of the true colour VIS ({bands, min, max}) in words, its reflectance with 3 decimals: it has no colour
	// bar
	function rgbCaption(vis) {
		function reflectance(x) {
			var s = String(Math.round(x * 1000) / 1000);
			return state.lang === 'es' ? s.replace('.', ',') : s;
		}
		return fmt(t('rgbLegend'), reflectance(vis.min), reflectance(vis.max));
	}

	// The legend of the true colour VIS: TITLE and its range, or only its range below the colour bar of the index of
	// the same map (BELOW: the layer Both)
	function rgbLegend(vis, title, below) {
		if (!below) {
			legend.clear();
			legend.add(ui.Label(title, {fontWeight: 'bold', fontSize: '12px', margin: '0 0 4px 0'}));
		}
		legend.add(ui.Label(rgbCaption(vis), {fontSize: '11px', margin: below ? '4px 0 0 0' : '0'}));
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

	// The region FC, named NAME (null: by the names of its features, then with SUFFIX), which is SPEC as areas.region
	// takes it (the region of the parameters of the analysis: {wdpa_id: id}, {bbox: [w, s, e, n]}...); ADMIN: the level of
	// the administrative unit it is (1 and 2: FAO GAUL 2025; 3: the municipalities of Spain of the IGN), whose credits
	// are shown with it
	function setRegion(fc, name, spec, suffix, admin) {
		oneMap();  // its layer on the map shown
		var named = name !== null && name !== undefined;
		state.region = fc;
		state.regionName = named ? name : t('loadingRegion');
		state.regionSpec = spec || null;
		state.regionAdmin = admin || null;
		state.info = null;
		if (regionLayer) map.layers().remove(regionLayer);
		regionLayer = map.addLayer(ee.FeatureCollection(fc).style({color: 'ffff00', fillColor: '00000000', width: 2}), {},
			named ? name : '');
		var ask = {info: mo.regionInfo(fc), n: fc.size()};
		if (!named) ask.names = fc.aggregate_array('name');
		ee.Dictionary(ask).evaluate(function (d, error) {
			if (error) return fail(error);
			if (state.region !== fc) return;
			state.info = d.info;
			state.info.n = d.n;
			state.info.crs = mo.regionCrs(d.info);  // areas.auto_crs: the UTM zone of the centre, or EPSG:6933 if wide
			if (!named) {
				state.regionName = (d.names || []).join(', ') + (suffix || '');
				if (regionLayer && regionLayer.setName) regionLayer.setName(state.regionName);
			}
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
		if (state.mode === 'sea') {  // the sea at the point: {sea_at: [lon, lat]}
			var sea = mo.seaAt(coords.lon, coords.lat);
			sea.aggregate_array('name').evaluate(function (names, error) {
				if (error) return fail(error);
				if (!(names && names.length)) return message(t('noSea'), true);
				setRegion(sea, names[0], {sea_at: [coords.lon, coords.lat]}, undefined, 'sea');
			});
			return;
		}
		if (state.mode !== 'ecoregion' && state.mode !== 'island' && state.mode !== 'biome') return;
		var biome = state.mode === 'biome', fc, point = [coords.lon, coords.lat], spec = {};
		if (biome) {  // a whole biome spans continents: its part in the map view, the region {biome_at, within: bbox}
			var inside = mo.bboxRegion(map.getBounds()).geometry(mo.WITHIN_MAX_ERROR);
			fc = mo.withinRegion(mo.biomeAt(coords.lon, coords.lat, inside), inside);
			spec = {biome_at: point, within: {bbox: map.getBounds()}};
		} else {
			fc = state.mode === 'island' ? mo.islandAt(coords.lon, coords.lat) : mo.ecoregionAt(coords.lon, coords.lat);
			spec[state.mode === 'island' ? 'island_at' : 'ecoregion_at'] = point;
		}
		if (biome) message(t('loadingRegion'));
		fc.aggregate_array('name').evaluate(function (names, error) {
			if (error) return fail(error);
			if (!(names && names.length)) return biome ? message(t('noBiome'), true) : null;
			if (biome) results.style().set('shown', false);
			setRegion(fc, biome ? names[0] + ' · ' + t('mapView') : names[0], spec);
		});
	});

	// The GeoJSON of GEOMETRY, drawn on the map (a geometry of the client: no request to Earth Engine), or null
	function geojsonOf(geometry) {
		try {
			return geometry.toGeoJSON();
		} catch (err) {
			return null;
		}
	}

	drawing.onDraw(function (geometry) {
		if (state.drawingLine) {  // the line of a profile (Gradients), not a region
			state.drawingLine = false;
			drawing.setShape(null);
			drawing.setDrawModes(['polygon']);
			drawing.setShown(state.mode === 'draw');
			state.line = geojsonOf(geometry);  // the line of transect in the parameters
			return guarded(function () { profile(geometry); })();
		}
		if (state.mode !== 'draw') return;
		drawing.setShape(null);
		var shape = geojsonOf(geometry);
		setRegion(ee.FeatureCollection([ee.Feature(geometry, {name: t('polygon')})]), t('polygon'),
			shape ? {geojson: {type: 'Feature', geometry: shape, properties: {name: t('polygon')}}} : null);
	});

	function searchWdpa() {
		state.wdpaItems = null;
		message(t('computing'));
		mo.findProtectedAreas(state.wdpaText, 30, state.ramsar).evaluate(function (fc, error) {
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

	// The administrative units of the level chosen whose name contains the text: of FAO GAUL 2025 (levels 1 and 2, in
	// the country if given) or, level 3, the municipalities of Spain (by name, whatever the case and accents, or by the
	// code of the INE), listed as 'name (province)' and their code. The answer of a search whose level (or kind of
	// region) was changed meanwhile is left out: its codes are of another level, and chooseAdmin builds the region of
	// the level chosen
	function searchAdmin() {
		state.adminItems = null;
		message(t('computing'));
		var level = state.adminLevel, municipal = Number(level) === 3;
		var found = municipal ? mo.findMunicipalities(state.adminText, 30) :
			mo.findAdminUnits(state.adminText, level, state.adminCountry || null, 30);
		found.evaluate(function (fc, error) {
			if (state.mode !== 'admin' || Number(state.adminLevel) !== Number(level)) return;
			if (error) return fail(error);
			state.adminNames = {};
			state.adminItems = fc.features.map(function (f) {
				var p = f.properties;
				if (municipal) {
					state.adminNames[p.code] = p.name + ' (' + p.province + ')';
					return {value: p.code, label: state.adminNames[p.code] + ' · INE ' + p.code};
				}
				var code = p['GAUL' + level + '_CODE'];
				state.adminNames[code] = p.DISP_EN;
				return {value: code, label: p.DISP_EN + ' (GAUL ' + code + ')'};
			});
			results.style().set('shown', false);
			if (!state.adminItems.length) message(t('noUnit'));
			render();
		});
	}

	function chooseAdmin(code) {
		state.adminCode = code;
		results.style().set('shown', false);
		var spec = {};
		spec['admin' + state.adminLevel] = code;  // level 3: the code of the INE (a string of 5 digits)
		setRegion(mo.adminRegion(state.adminLevel, code), state.adminNames[code], spec, undefined, Number(state.adminLevel));
	}

	// The oceans and seas whose name contains the text (the sea areas of the IHO, Marine Regions), listed as 'name ·
	// area (MRGID)'; the answer of a search left behind (another mode chosen meanwhile) is left out
	function searchSeas() {
		message(t('computing'));
		mo.findSeas(state.seaText, 30).evaluate(function (fc, error) {
			if (state.mode !== 'sea') return;
			if (error) return fail(error);
			state.seaNames = {};
			state.seaItems = fc.features.map(function (f) {
				var p = f.properties;
				state.seaNames[p.mrgid] = p.name;
				return {value: p.mrgid, label: p.name + ' · ' + bigNum(p.area_km2) + ' km² (MRGID ' + p.mrgid + ')'};
			});
			results.style().set('shown', false);
			if (!state.seaItems.length) message(t('noSea'));
			render();
		});
	}

	function chooseSea(mrgid) {
		state.seaId = mrgid;
		results.style().set('shown', false);
		setRegion(mo.seaRegion([mrgid]), state.seaNames[mrgid], {sea: mrgid}, undefined, 'sea');
	}

	function chooseWdpa(id) {
		state.wdpaId = id;
		var label = state.wdpaNames[id];
		message(t('loadingRegion'));
		mo.wdpaGeometries([id]).evaluate(function (info, error) {
			if (error) return fail(error);
			results.style().set('shown', false);
			setRegion(mo.wdpaRegion(info), label, {wdpa_id: id});
		});
	}

	function regionWidgets() {
		var w = [header(t('region'))];
		var modes = ['wdpa', 'admin', 'ecoregion', 'biome', 'island', 'sea', 'view', 'draw'].map(function (m) {
			return {value: m, label: t('mode_' + m)};
		});
		w.push(select(modes, state.mode, function (m) {
			state.mode = m;
			oneMap();  // the tools to draw are those of the map of the app
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
			w.push(ui.Checkbox({label: t('ramsar'), value: state.ramsar, style: SMALL,
				onChange: function (v) { state.ramsar = v; }}));
			if (state.wdpaItems && state.wdpaItems.length) {
				w.push(ui.Select({items: state.wdpaItems, placeholder: t('chooseArea'), value: state.wdpaId,
					onChange: chooseWdpa, style: {width: '340px'}}));
			}
		} else if (state.mode === 'admin') {
			var municipal = Number(state.adminLevel) === 3;  // the municipalities of Spain: no country to give
			var name = ui.Textbox({placeholder: t(municipal ? 'adminHint3' : 'adminHint'), value: state.adminText,
				onChange: function (v) { state.adminText = v; }, style: {width: '200px'}});
			var country = ui.Textbox({placeholder: t('countryHint'), value: state.adminCountry,
				onChange: function (v) { state.adminCountry = v; }, style: {width: '130px'}});
			w.push(select([1, 2, 3].map(function (n) { return {value: n, label: t('level' + n)}; }), state.adminLevel,
				function (v) { state.adminLevel = v; state.adminItems = null; render(); }, '250px'));
			if (municipal) w.push(ui.Label(t('level3Help'), SMALL));
			w.push(municipal ? name : row(name, country));
			w.push(button(t('search'), function () {
				state.adminText = name.getValue();
				if (!municipal) state.adminCountry = country.getValue();
				searchAdmin();
			}));
			if (state.adminItems && state.adminItems.length) {
				w.push(ui.Select({items: state.adminItems, placeholder: t('chooseUnit'), value: state.adminCode,
					onChange: chooseAdmin, style: {width: '340px'}}));
			}
		} else if (state.mode === 'island') {
			w.push(ui.Label(t('islandHelp'), SMALL));
		} else if (state.mode === 'sea') {
			w.push(ui.Label(t('seaHelp'), SMALL));
			var seaName = ui.Textbox({placeholder: t('seaHint'), value: state.seaText,
				onChange: function (v) { state.seaText = v; }, style: {width: '200px'}});
			w.push(row(seaName, button(t('search'), function () {
				state.seaText = seaName.getValue();
				searchSeas();
			})));
			if (state.seaItems && state.seaItems.length) {
				w.push(ui.Select({items: state.seaItems, placeholder: t('chooseSea'), value: state.seaId,
					onChange: chooseSea, style: {width: '340px'}}));
			}
		} else if (state.mode === 'ecoregion') {
			w.push(ui.Label(t('clickHelp'), SMALL));
		} else if (state.mode === 'biome') {
			w.push(ui.Label(t('biomeHelp'), SMALL));
		} else if (state.mode === 'view') {
			w.push(button(t('useView'), function () {
				var b = map.getBounds();
				setRegion(mo.bboxRegion(b, t('mapView')), t('mapView'), {bbox: b});
			}));
		} else {
			w.push(ui.Label(t('drawHelp'), SMALL));
			w.push(button(t('drawAgain'), function () {
				oneMap();
				drawing.layers().reset();
				drawing.setShape('polygon');
			}));
		}
		if (state.region) {
			var area = state.info ? ' · ' + bigNum(km2(state.info.total)) + ' km²' : '';
			w.push(ui.Label(t('regionIs') + state.regionName + area, {fontSize: '12px', color: '#1a73e8'}));
			if (state.regionAdmin) {  // the credits of its data (FAO GAUL, IGN, Marine Regions) and their references
				var cited = mo.adminCredits(state.regionAdmin);
				cited.credits.forEach(function (c) { w.push(ui.Label(c, SMALL)); });
				cited.references.forEach(function (r) {
					w.push(ui.Label(t('references') + ': ' + r.citation, SMALL, r.url));
				});
			}
		}
		return w;
	}

	// Variable, period, filters -------------------------------------------------------------------------------------

	// The entry of what the panel computes: the variable of the catalog chosen, or, in the themes of the data of Earth
	// Engine (catalog.OTHER_THEMES), the data read (dataEntry)
	function entry() {
		return isData() ? dataEntry() : mo.byRef(state.ref);
	}

	// Whether the theme chosen is one of the data of Earth Engine outside the catalog: any image or collection by its
	// ID (earth_engine) or the GEE Community Catalog (community)
	function isData() {
		return mo.otherThemes().some(function (th) { return th.key === state.theme; });
	}

	// The number written in TEXT (a comma is a decimal point), null if empty, or an error naming WHAT
	function numberOf(text, what) {
		text = String(text === null || text === undefined ? '' : text).trim().replace(',', '.');
		if (!text) return null;
		if (isNaN(Number(text))) throw new Error(fmt(t('badNumber'), what, text));
		return Number(text);
	}

	// The bands of the data read that are checked to be combined, in the order of the data (jan to dec)
	function chosenBands() {
		var d = state.data;
		return d.bands.filter(function (b) { return d.chosen.indexOf(b) >= 0; });
	}

	// The entry of the data of Earth Engine of the panel (mo.customEntry: its ID read, band or the bands checked and
	// their reducer, use, scale, offset and unit), or, while it cannot be computed (no ID read, fewer than two bands
	// checked to combine, a scale or a unit that are not), one with the reason (problem), so that the panel can still be
	// drawn and ready() says what is missing
	function dataEntry() {
		var d = state.data;
		var several = d.combine === 'sum' || d.combine === 'mean';
		var band = several ? chosenBands() : d.band, first = several ? band[0] : d.band;
		try {
			if (!d.asset) throw new Error(t('readFirst'));
			if (several && band.length < 2) throw new Error(t('combineTwo'));
			return mo.customEntry({asset: d.asset, type: d.type, dated: d.dated, band: band,
				reducer: several ? d.combine : null, use: d.use, m: d.scales[first],
				scale: numberOf(d.scale, t('bandScale')), offset: numberOf(d.offset, t('bandOffset')), unit: d.unit});
		} catch (err) {
			return {custom: true, static: d.use === 'image', col: d.asset || '', band: band || '',
				reducer: several ? d.combine : null, m: d.scales[first] || 1, unit: '',
				problem: err.message || String(err)};
		}
	}

	// Reads the ID TEXT in Earth Engine (mo.assetInfo, asynchronous): its type, bands and their pixel size, and where
	// it comes from; the band, use and the rest of the panel are then those of what it is, and THEN(error, info) is
	// called, if given (the parameters applied: their band, scale... after the read)
	function readAsset(text, then) {
		var id = mo.assetId(text);
		if (!id) return message(t('readFirst'), true);
		var d = state.data;
		var at = run;  // a computation started after this read keeps its answer in the results panel
		d.text = id;
		d.reading = id;
		d.asset = null;
		d.error = null;
		render();
		mo.assetInfo(id, function (error, info) {
			if (state.data.reading !== id) return;  // another ID was read since
			d.reading = null;
			if (error) {
				d.error = error.message || String(error);  // under the ID too (dataWidgets), where it stays
				if (then) then(error);
				render();
				if (at === run) message(d.error, true);
				return;
			}
			['asset', 'type', 'dated', 'use', 'bands', 'scales', 'title', 'source', 'page', 'licence'].forEach(function (k) {
				d[k] = info[k] === undefined ? null : info[k];
			});
			d.band = info.bands[0] || null;
			d.combine = 'one';  // one band again, none checked to combine: those of another ID
			d.chosen = [];
			d.scale = d.offset = d.unit = '';  // Earth Engine does not say them (they are in the page of the dataset)
			if (then) then(null, info);
			render();
		});
	}

	// The theme and the dataset of the GEE Community Catalog (mo.communityThemes and mo.communityDatasets, from the
	// copy of its index in the app): choosing a dataset reads its ID
	function communityWidgets() {
		var d = state.data;
		var w = [header(t('communityTheme'))];
		w.push(ui.Select({items: mo.communityThemes(state.lang).map(function (th) {
			return {value: th.theme, label: th.name + ' (' + th.datasets + ')'};
		}), placeholder: t('communityTheme'), value: d.communityTheme, onChange: function (v) {
			d.communityTheme = v;
			d.communityId = null;
			render();
		}, style: {width: '340px'}}));
		if (d.communityTheme) {
			w.push(header(t('dataset')));
			w.push(ui.Select({items: mo.communityDatasets(d.communityTheme).map(function (r) {
				return {value: r.id, label: r.title + ' · ' + t('type_' + r.type)};
			}), placeholder: t('chooseDataset'), value: d.communityId, onChange: function (id) {
				d.communityId = id;
				readAsset(id);
			}, style: {width: '340px'}}));
		}
		var c = mo.CATALOG.community || {};
		w.push(ui.Label(fmt(t('communityNote'), c.date || ''), SMALL, c.site));
		return w;
	}

	// The data of Earth Engine by its ID: the ID and Read, then what it is (title, source, licence and page), its band,
	// its use (images with dates or a fixed image), the scale and offset of its stored values and their unit
	// The search of the Earth Engine data catalog (its copy in catalog.js: without Earth Engine): the collections with
	// data in the years of the period, the images (fixed) whatever their dates; the dataset chosen is read as an ID written
	function catalogWidgets() {
		var w = [header(t('catalogSearch'))];
		var box = ui.Textbox({placeholder: t('catalogHint'), value: state.catalogText,
			onChange: function (v) { state.catalogText = v; }, style: {width: '250px'}});
		w.push(row(box, button(t('search'), function () {
			var years = state.period.map(function (d) { return Number(String(d).slice(0, 4)); });
			state.catalogFound = mo.searchCatalog(box.getValue(), years[0], years[1], 30);
			render();
		})));
		var found = state.catalogFound;
		if (found && !found.length) w.push(ui.Label(t('catalogNone'), SMALL));
		if (found && found.length) {
			w.push(ui.Label(fmt(t('catalogFound'), found.length), SMALL));
			w.push(select(found.map(function (d) {
				return {value: d.id, label: d.title + ' (' + (d.first || '?') + '-' + (d.last || '…') + ')'};
			}), null, function (v) {
				state.data.text = v;
				readAsset(v);
			}, '330px'));
		}
		return w;
	}

	function dataWidgets() {
		var d = state.data;
		var w = state.theme === 'community' ? communityWidgets() : state.theme === 'earth_engine' ? catalogWidgets() : [];
		w.push(header(t('assetId')));
		var id = ui.Textbox({placeholder: t('assetHint'), value: d.text, onChange: function (v) { d.text = v; },
			style: {width: '250px'}});
		w.push(row(id, button(t('read'), function () { readAsset(id.getValue()); })));
		if (d.reading) return w.concat([ui.Label(t('reading'), SMALL)]);
		if (d.error) return w.concat([ui.Label(d.error, {fontSize: '12px', color: '#b00020', whiteSpace: 'pre-wrap'})]);
		if (!d.asset) return w.concat([ui.Label(t('readFirst'), SMALL)]);
		var source = {};
		source[mo.DATA_CATALOG] = 'src_data';
		source[mo.COMMUNITY_CATALOG] = 'src_community';
		source[mo.EE_ASSET] = 'src_asset';
		w.push(ui.Label([d.title, t(source[d.source] || 'src_asset'), t('type_' + d.type),
			d.licence ? t('licence') + ': ' + d.licence : t('licenceInPage')].join(' · '), SMALL));
		if (d.page) w.push(ui.Label(t('datasetPage'), {fontSize: '12px', margin: '0 8px'}, d.page));
		// one band, or several combined on each pixel (their sum or mean: band_reducer in the package)
		if (d.bands.length > 1 || d.combine !== 'one') {
			w.push(row(ui.Label(t('combine')), select(['one', 'sum', 'mean'].map(function (x) {
				return {value: x, label: t('combine_' + x)};
			}), d.combine, function (v) {
				if (v !== 'one' && !d.chosen.length && d.band) d.chosen = [d.band];  // the band chosen, then the others
				d.combine = v;
				render();
			}, '220px')));
		}
		if (d.combine === 'one') {
			w.push(row(ui.Label(t('band')), select(d.bands.map(function (b) {
				return {value: b, label: b + ' · ' + num(d.scales[b]) + ' m'};
			}), d.band, function (v) {
				// the scale, offset and unit are those of each band (bio01 of WorldClim is stored in tenths of a degree,
				// bio12 in mm): empty again, as the QGIS plugin fills them from the record of the band, which the app
				// cannot read
				if (v !== d.band) d.scale = d.offset = d.unit = '';
				d.band = v;
				render();
			}, '220px')));
		} else {
			// the bands to combine, with their pixel size: the scale, offset and unit are those of all of them
			w.push(ui.Label(t('bands'), SMALL));
			d.bands.forEach(function (b) {
				w.push(check(b + ' · ' + num(d.scales[b]) + ' m', d.chosen.indexOf(b) >= 0, function (v) {
					d.chosen = d.chosen.filter(function (x) { return x !== b; });
					if (v) d.chosen.push(b);
					render();
				}));
			});
			var chosen = chosenBands();
			var sizes = chosen.map(function (b) { return Number(d.scales[b]); });
			if (sizes.some(function (s) { return s !== sizes[0]; })) {  // combined on the pixels of the first band
				w.push(ui.Label(fmt(t('combineScales'), num(sizes[0])), {fontSize: '12px', color: '#b06000'}));
			}
			w.push(ui.Label(t('combineNote'), SMALL));
		}
		var use = select(['collection', 'image'].map(function (x) { return {value: x, label: t('use_' + x)}; }),
			d.dated ? d.use : 'image', function (v) {
				d.use = v;
				render();
			}, '220px');
		// an image has no dates, nor have the tiles of a collection of them (a DEM): only their mosaic, a fixed image
		use.setDisabled(!d.dated);
		w.push(row(ui.Label(t('useAs')), use));
		function field(key, hint, width) {
			return ui.Textbox({placeholder: hint, value: d[key], onChange: function (v) { d[key] = v.trim(); },
				style: {width: width}});
		}
		w.push(row(ui.Label(t('bandScale')), field('scale', '1', '70px'), ui.Label(t('bandOffset')),
			field('offset', '0', '70px')));
		w.push(row(ui.Label(t('unit')), field('unit', t('unitHint'), '180px')));
		w.push(ui.Label(t('bandNote'), SMALL));
		if (d.use === 'image' || !d.dated) w.push(ui.Label(t('staticNote'), SMALL));
		return w;
	}

	// The entries of the variable menu: those of THEME (a key of catalog.THEMES; all of them without it), without RBR
	// and RdNBR, which compare two periods (Burn severity)
	function variableItems(theme) {
		return mo.variables().filter(function (e) {
			return !e.two_periods && (!theme || e.theme === theme);
		}).sort(function (a, b) {
			return a.index < b.index ? -1 : a.index > b.index ? 1 : a.sensor < b.sensor ? -1 : a.sensor > b.sensor ? 1 :
				a.ref - b.ref;
		}).map(function (e) {
			return {value: e.ref, label: [e.index, e.sensor, e.m + ' m', e.col.split('/').pop()].join(' · ')};
		});
	}

	// The theme KEY ('all': every variable): its variables in the menu, and the first of them if the one chosen is not
	// one of them; the themes of the data of Earth Engine have no variables (dataWidgets)
	function setTheme(key) {
		state.theme = key;
		if (isData()) return render();
		var items = variableItems(key === 'all' ? null : key);
		if (items.length && !items.some(function (i) { return i.value === state.ref; })) return setVariable(items[0].value);
		// the variable stays (and the pixel filters chosen for it), but its only metric (SCF, CF) again: the themes of the
		// data of Earth Engine let the metrics change meanwhile
		var only = mo.byRef(state.ref).metric;
		if (only) state.mapMetric = state.stepMetric = state.trendMetric = state.animMetric = only;
		render();
	}

	// Whether the theme chosen has the analysis NAME of its own (e.g. burn_severity, of the fires)
	function themeHas(name) {
		return state.theme === 'all' || mo.themes().some(function (th) {
			return th.key === state.theme && (th.analyses || []).indexOf(name) >= 0;
		});
	}

	function setVariable(ref) {
		var before = entry();
		state.ref = ref;
		var e = entry();
		var fixed = mo.fixedFilters(e);  // the SCF: clouds and water, always
		if (fixed && !state.chosenQuality) {
			// the filters chosen, those of the right axis of a profile (otherQuality): with that of what the variable
			// before measures back on, unchecked only because of it (the snow of the NDSI), as the QGIS plugin keeps it
			state.chosenQuality = JSON.parse(JSON.stringify(state.quality));
			mo.FILTERS.forEach(function (f) {
				if (before && (mo.MEASURES[f] || []).indexOf(before.index) >= 0) state.chosenQuality[f] = true;
			});
		}
		if (!fixed) state.chosenQuality = null;
		mo.FILTERS.forEach(function (f) {
			state.quality[f] = fixed ? fixed.indexOf(f) >= 0 : (mo.MEASURES[f] || []).indexOf(e.index) < 0;
		});
		// its only metric (SCF), also of each frame of the animation
		if (e.metric) state.mapMetric = state.stepMetric = state.trendMetric = state.animMetric = e.metric;
		render();
	}

	// services._ylabel: title of the y axis of the charts of the entry E (with the statistic STAT of the region, and the
	// metric between the years INTERANNUAL of a profile by day of the year), the unit after its axis title if it has one
	// (e.g. 'Snow Cover Frequency (SCF) [%]'); of a coefficient of variation, after its name
	function axisTitle(e, metric, stat, interannual) {
		var unit = unitText(e, metric, interannual || null, stat);
		if ((!e.static && (mo.isCv(metric) || mo.isCv(interannual))) || mo.isCv(stat)) {
			return (t('cvAxis') + ' ' + (unit || '')).trim();
		}
		return e.axis ? (e.axis + ' ' + (unit || '')).trim() : unit;
	}

	// The unit of the values of the entry E aggregated with METRIC as the titles show it: that of the catalog, or that
	// given for the data of Earth Engine, in UDUNITS, between brackets as those of the catalog ('[mm]', services._ylabel).
	// A fixed layer has no metric (services.make_spec: none for an image), whatever the select greyed out holds: the
	// mosaic of a collection of rates per month is still a rate, not their sum
	function unitText(e, metric, interannual, stat) {
		var unit = mo.unitOf(e, e.static ? null : metric, e.static ? null : interannual, stat);
		return e.custom && unit && unit.charAt(0) !== '[' ? '[' + unit + ']' : unit;
	}

	// The select of the metric of the images, fixed at the only metric of the variable if it has one (SCF: the mean),
	// greyed out also for the fixed layers without dates (elevation, slope)
	// The key of the note under the variable E with a single metric: the SCF of Landsat or Sentinel-2 (the same
	// rules) or of MODIS, the snow cover days or the cloud frequency, or null
	function variableNote(e) {
		if (!e.metric) return null;
		if (e.index === 'SCF') return e.sensor === 'Modis' ? 'scfModisNote' : 'scfNote';
		return {SCD: 'scdNote', CF: 'cfNote'}[e.index] || null;
	}

	function metricSelect(value, onChange) {
		var only = entry().metric;
		// the only metric of a variable that the list of the others has not (the days of the snow cover days)
		var metrics = METRICS.concat(only && METRICS.indexOf(only) < 0 ? [only] : [])
			.map(function (m) { return {value: m, label: metricName(m)}; });
		var s = select(metrics, only || value, onChange);
		s.setDisabled(Boolean(only) || Boolean(entry().static));
		return s;
	}

	// Greys out the widgets W and those of their panels (the options of the dates, for a fixed layer); returns W
	function disable(w) {
		w.forEach(function (x) {
			if (typeof x.widgets === 'function') x.widgets().forEach(function (y) { disable([y]); });
			else if (typeof x.setDisabled === 'function') x.setDisabled(true);
		});
		return w;
	}

	function variableWidgets() {
		var e = entry();
		// the themes of the catalog, then those of the data of Earth Engine outside it (as services.themes)
		var themes = mo.themes().concat(mo.otherThemes()).map(function (th) {
			return {value: th.key, label: th[state.lang] || th.en};
		});
		var w = [header(t('theme')), select(themes.concat([{value: 'all', label: t('allThemes')}]), state.theme,
			setTheme, '340px')];
		if (isData()) {
			w = w.concat(dataWidgets());
		} else {
			w.push(header(t('variable')));
			w.push(select(variableItems(state.theme === 'all' ? null : state.theme), state.ref, setVariable, '340px'));
			var name = state.lang === 'en' ? e.vname_en : e.vname;
			w.push(ui.Label([name, e.unit, (state.lang === 'en' ? 'pixel ' : 'píxel ') + e.m + ' m', e.dr, e.ft]
				.filter(function (x) { return x; }).join(' · '), SMALL));
			var note = variableNote(e);  // how the variables with a single metric are computed
			if (note) w.push(ui.Label(t(note), SMALL));
			if (e.static) w.push(ui.Label(t('staticNote'), SMALL));
			if (mo.isCategorical(e)) w.push(ui.Label(t('categoricalNote'), SMALL));
		}
		var dates = [header(t('period'))];  // greyed out for a fixed layer without dates (elevation, slope)
		dates.push(row(box(state.period[0], function (v) { state.period[0] = v.trim(); }), ui.Label(t('to')),
			box(state.period[1], function (v) { state.period[1] = v.trim(); })));
		dates.push(check(t('season'), state.seasonOn, function (v) {
			state.seasonOn = v;
			render();
		}));
		if (state.seasonOn) {
			dates.push(row(box(state.season[0], function (v) { state.season[0] = v.trim(); }, '70px'), ui.Label(t('to')),
				box(state.season[1], function (v) { state.season[1] = v.trim(); }, '70px')));
		}
		dates.push(check(t('compare'), state.compareOn, function (v) {
			state.compareOn = v;
			render();
		}));
		if (state.compareOn) {
			dates.push(row(ui.Label(t('other') + ':'), box(state.other[0], function (v) { state.other[0] = v.trim(); }),
				ui.Label(t('to')), box(state.other[1], function (v) { state.other[1] = v.trim(); })));
		}
		var datedWhere = state.whereOn && !mo.byRef(whereRef()).static;  // its period is that of the panel
		w = w.concat(e.static && !datedWhere ? disable(dates) : dates);
		w.push(header(t('filters')));
		// fixed filters (the SCF): all of them greyed out, those always on checked
		var fixed = mo.fixedFilters(e);
		var available = mo.filters(e, {clouds: true, water: true, snow: true, aerosols: true});
		mo.FILTERS.forEach(function (f) {
			var c = check(t(f), state.quality[f] && available[f], function (v) {
				state.quality[f] = v;
				render();
			});
			c.setDisabled(Boolean(fixed) || !available[f]);
			w.push(c);
		});
		if (fixed) w.push(ui.Label(e.custom ? t('customFilters') : t('fixedFilters'), SMALL));
		if (e.sensor === 'Sentinel-2') {
			w.push(check(t('cloudScore'), state.quality.cloud_score !== null, function (v) {
				state.quality.cloud_score = v ? 0.6 : null;
			}));
		}
		mo.conflicts(e, state.quality).forEach(function (f) {
			w.push(ui.Label(fmt(t('conflict'), t(f)), {fontSize: '12px', color: '#b06000'}));
		});
		w.push(header(t('whereHeader')));
		w.push(check(t('whereOn'), state.whereOn, function (v) {
			state.whereOn = v;
			render();
		}));
		if (state.whereOn) {
			w.push(select(variableItems(), whereRef(), function (ref) {
				state.whereRef = ref;
				render();
			}, '340px'));
			var we = mo.byRef(whereRef());
			if (mo.isCategorical(we)) {  // its classes to keep or to leave out, by their codes (found by their names)
				w.push(row(select([{value: 'classes', label: t('whereKeep')}, {value: 'exclude', label: t('whereExclude')}],
					state.whereKeep, function (v) { state.whereKeep = v; }, '200px'),
					ui.Textbox({placeholder: t('whereCodes'), value: state.whereCodes, style: {width: '120px'},
						onChange: function (v) { state.whereCodes = v.trim(); }})));
				var found = ui.Label('', SMALL);
				var search = ui.Textbox({placeholder: t('whereFind'), value: state.whereFind, style: {width: '200px'},
					onChange: function (v) {
						state.whereFind = v;
						var hits = v ? mo.findClasses(we, v, 12, state.lang) : [];
						found.setValue(hits.length ? fmt(t('whereFound'), hits.map(function (c) {
							return c.code + ' ' + c.name;
						}).join('; ')) : '');
					}});
				w.push(search);
				w.push(found);
				if (we.classes === 'biomes') {  // few: all of them, with their codes
					w.push(ui.Label(mo.layerClasses(we, state.lang).map(function (c) {
						return c.code + ' ' + c.name;
					}).join('; '), SMALL));
				}
				w.push(ui.Label(t('whereClassNote'), SMALL));
			} else {
				w.push(row(ui.Label(t('between')), box(state.whereMin, function (v) { state.whereMin = v.trim(); }, '70px'),
					ui.Label(t('and')), box(state.whereMax, function (v) { state.whereMax = v.trim(); }, '70px'),
					ui.Label(we.unit || '')));
				w.push(ui.Label(t('whereNote'), SMALL));
			}
		}
		return w;
	}

	// The variable of the condition of «Only the pixels where»: by default the elevation of the Copernicus DEM
	function whereRef() {
		if (state.whereRef === null) {
			state.whereRef = mo.variables().filter(function (e) {
				return e.index === 'ELEVATION';
			}).map(function (e) { return e.ref; })[0];
		}
		return state.whereRef;
	}

	// services.make_spec(where=...): the condition of «Only the pixels where», with PERIOD (default: that of the
	// panel) when its variable has dates (the same pixels for every step and for the other period of a comparison;
	// for a fire, the period before it); null if off
	function whereArgs(period) {
		period = period || state.period;
		var lc = landcoverArgs();
		if (!state.whereOn) return lc ? [lc] : null;
		var c = {ref: whereRef()};
		var we = mo.byRef(c.ref);
		if (mo.isCategorical(we)) {  // its classes to keep or to leave out (checked now, as the package does)
			if (!state.whereCodes) throw new Error(t('noCodes'));
			c[state.whereKeep] = mo.checkClasses(we, state.whereCodes, state.whereKeep);
			return lc ? [c, lc] : [c];
		}
		[['min', state.whereMin], ['max', state.whereMax]].forEach(function (x) {
			var text = String(x[1] || '').replace(',', '.');
			if (!text) return;
			if (isNaN(Number(text))) throw new Error(fmt(t('badLimit'), x[1]));
			c[x[0]] = Number(text);
		});
		if (c.min === undefined && c.max === undefined) throw new Error(t('noLimit'));
		if (!mo.byRef(c.ref).static) {
			checkPeriod(period);
			c.period = period.slice();
		}
		return lc ? [c, lc] : [c];
	}

	// The year of the land cover map chosen: the one chosen if the map has it, otherwise its default (its last one; for
	// Dynamic World, the last whole year)
	function landcoverYear() {
		var m = mo.landcoverMap(state.landcoverMap);
		if (mo.landcoverYears(m).indexOf(state.landcoverYear) < 0) state.landcoverYear = mo.landcoverDefaultYear(m);
		return state.landcoverYear;
	}

	// The land cover condition of where of the land cover mask (landcover.py), or null if it is off
	function landcoverArgs() {
		if (!state.landcoverOn) return null;
		if (!state.landcoverExclude.length) throw new Error(t('noLandcover'));
		return {landcover: state.landcoverMap, year: landcoverYear(), exclude: state.landcoverExclude.slice()};
	}

	// The land cover mask, before the variable: unfolds when checked, with the map, its year and the broad land covers
	// to leave out of every result (a condition of where, see landcoverArgs)
	function landcoverWidgets() {
		var w = [header(t('landcoverHeader')), check(t('landcoverOn'), state.landcoverOn, function (v) {
			state.landcoverOn = v;
			render();
		})];
		if (!state.landcoverOn) return w;
		var maps = mo.landcoverMaps().map(function (m) {
			return {value: m.key, label: [m.name, m.m + ' m', m.coverage].join(' · ')};
		});
		w.push(select(maps, state.landcoverMap, function (key) {
			state.landcoverMap = key;
			render();
		}, '340px'));
		var m = mo.landcoverMap(state.landcoverMap);
		var years = mo.landcoverYears(m).slice().reverse().map(function (y) { return {value: y, label: String(y)}; });
		w.push(row(ui.Label(t('landcoverYear')), select(years, landcoverYear(), function (y) {
			state.landcoverYear = Number(y);
		}, '90px')));
		w.push(ui.Label(t('landcoverLeaveOut'), SMALL));
		mo.landcoverClasses().forEach(function (c) {
			var codes = mo.landcoverCodes(m, [c.key]);  // the classes of the map in it, e.g. «Water (511, 512, ...)»
			w.push(check((c[state.lang] || c.en) + (codes.length ? ' (' + codes.join(', ') + ')' : ''),
				state.landcoverExclude.indexOf(c.key) >= 0, function (v) {
					state.landcoverExclude = state.landcoverExclude.filter(function (k) { return k !== c.key; });
					if (v) state.landcoverExclude.push(c.key);
				}));
		});
		w.push(ui.Label(t('landcoverNote'), SMALL, mo.CATALOG.about.manual + (state.lang === 'en' ?
			'/Concepts#land-cover-mask' : '/Conceptos#máscara-de-usos-del-suelo')));
		return w;
	}

	// The text of the condition for the titles, e.g. «ELEVATION ≥ 1500»
	function whereText() {
		var lc = state.landcoverOn && state.landcoverExclude.length ? mo.landcoverText(landcoverArgs(), state.lang) : null;
		if (!state.whereOn) return lc;
		var e = mo.byRef(whereRef());
		if (mo.isCategorical(e)) {  // e.g. «BIOME (RESOLVE) is 12 Mediterranean Forests, Woodlands & Scrub»
			var c = {ref: e.ref};
			c[state.whereKeep] = state.whereCodes;
			return mo.classText(c, state.lang) + (lc ? ', ' + lc : '');
		}
		var parts = [];
		if (state.whereMin) parts.push('≥ ' + state.whereMin);
		if (state.whereMax) parts.push('≤ ' + state.whereMax);
		return e.index + ' ' + parts.join(' ') + (e.unit ? ' ' + e.unit : '') + (lc ? ', ' + lc : '');
	}

	// Checks and specs ----------------------------------------------------------------------------------------------

	var DATE = /^\d{4}-\d{2}-\d{2}$/;
	var MONTH_DAY = /^\d{2}-\d{2}$/;

	function checkPeriod(p) {
		p.forEach(function (d) {
			if (!DATE.test(d) || isNaN(mo.date(d).getTime())) throw new Error(fmt(t('badDate'), d));
		});
	}

	// The spec of the variable over PERIOD (default: the period), or an Error with what is wrong; in the themes of
	// the data of Earth Engine, the spec of their entry (dataEntry), without pixel filters (they keep their own mask)
	function specOf(period, metric, ref) {
		period = period || state.period;
		checkPeriod(period);
		var season = null;
		if (state.seasonOn) {
			state.season.forEach(function (d) { if (!MONTH_DAY.test(d)) throw new Error(fmt(t('badDate'), d)); });
			season = state.season.slice();
		}
		var e = ref ? null : entry();
		if (e && e.problem) throw new Error(e.problem);
		var what = e && e.custom ? {entry: e, quality: {}} : {ref: ref || state.ref, quality: state.quality};
		var s = mo.spec({ref: what.ref, entry: what.entry, period: period.slice(), season: season, quality: what.quality,
			metric: metric || 'mean', where: ref ? null : whereArgs()});
		mo.windows(s.period, s.season);
		if (!ref) mo.used(s);  // the data of the values of the result, under it
		return s;
	}

	// The region checked for the entry E (and that the data of Earth Engine of the panel can be computed): true, or
	// false after showing why not
	function ready(e) {
		if (e.problem) {
			message(e.problem, true);
			return false;
		}
		if (!state.region || !state.info) {
			message(t('noRegion'), true);
			return false;
		}
		var area = km2(state.info.total);
		// a large area: only with coarse data (MODIS, the climate), on pixels of 1 to 10 km (mo.defaultScale)
		if (area > LIMITS.maxAreaKm2 && Number(e.m) < LIMITS.largeM) {
			message(fmt(t('largeOnly'), bigNum(area), bigNum(LIMITS.maxAreaKm2), LIMITS.largeM), true);
			return false;
		}
		if (area > LIMITS.maxLargeAreaKm2) {
			message(fmt(t('tooBig'), bigNum(area), bigNum(LIMITS.maxLargeAreaKm2)), true);
			return false;
		}
		var sea = mo.seaWarning(state.regionSpec, e);  // a variable of the land over a sea: a warning with the result
		if (sea) mo.noteWarning(sea);
		if (e.sensor === 'Sentinel-2' && area > LIMITS.s2AreaKm2) {
			message(fmt(t('s2TooBig'), bigNum(LIMITS.s2AreaKm2), bigNum(area)), true);
			return false;
		}
		// the same images given by their ID (COPERNICUS/S2_SR_HARMONIZED) cost as much, and so do those of any other
		// collection with pixels as fine (Sentinel-1); a fixed image is a single mosaic, as the elevation
		if (e.custom && !e.static && Number(e.m) <= LIMITS.fineM && area > LIMITS.s2AreaKm2) {
			message(fmt(t('fineTooBig'), mo.entryName(e), num(Number(e.m)), LIMITS.fineM, bigNum(LIMITS.s2AreaKm2),
				bigNum(area)), true);
			return false;
		}
		return true;
	}

	function guarded(f) {
		return function () {
			mo.resetNotes();  // a new computation: the warnings and data of its own specs
			try {
				f();
			} catch (e) {
				message(e.message || String(e), true);
			}
		};
	}

	// The title of a result of the entry E (or of what LABEL names: the variables of a profile by day of the year),
	// the region and its condition (where), and EXTRA
	function title(e, extra, label) {
		var where = whereText();
		return [label || mo.entryName(e), state.regionName + (where ? ' (' + where + ')' : '')].concat(extra || [])
			.join(' · ');
	}

	// The name of a file of the result NAME (its title) of the entry E, ending in SUFFIX: the data of Earth Engine by
	// the end of their ID, as services._file_stem
	function fileName(name, e, suffix) {
		suffix = suffix || '';
		if (e && e.custom && e.col) name = name.split(e.col).join(e.col.split('/').pop());
		return name.replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 90 - suffix.length) + suffix;
	}

	// Download of an image of the region as GeoTIFF (float, NoData -9999), with pixels as small as LIMITS allow (in a
	// large area, 1 to 10 km at least, as services._default_grid: mo.defaultScale); IMG
	// is the image, or a function of the pixel size that gives it (fixed layers: see mo.image). LABEL: that of the
	// button (default: Download GeoTIFF); SUFFIX: the end of the name of the file (the true colour: '_RGB', as
	// services.download_rgb)
	function downloadWidget(img, e, bands, name, label, suffix) {
		var panel = ui.Panel();
		suffix = suffix || '';
		panel.add(button(label || t('download'), function () {
			var native = Number(e.m), area = state.info.area;
			var res = mo.isLarge(area) ? mo.defaultScale(native, area, mo.TARGET_PIXELS) : native;
			var pixels = state.info.boundsArea / (res * res);
			var maxPixels = LIMITS.downloadBytes / (4 * bands.length);
			var scale = res * Math.max(1, Math.ceil(Math.sqrt(pixels / maxPixels)));
			panel.clear();
			panel.add(ui.Label(t('computing'), SMALL));
			ee.Image(typeof img === 'function' ? img(scale) : img).select(bands).toFloat().unmask(-9999, false).getDownloadURL({
				name: fileName(name, e, suffix),
				region: state.region.geometry().bounds(1000),
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

	// CSV of ROWS (their COLUMNS) as a download link of Earth Engine, named after NAME (of the entry E: see fileName)
	function csvWidget(rows, columns, name, e) {
		var panel = ui.Panel();
		panel.add(button(t('csv'), function () {
			panel.clear();
			panel.add(ui.Label(t('computing'), SMALL));
			ee.FeatureCollection(rows.map(function (r) {
				var p = {};
				columns.forEach(function (c) { p[c] = r[c] === null || r[c] === undefined ? '' : r[c]; });
				return ee.Feature(null, p);
			})).getDownloadURL('CSV', columns, fileName(name, e), function (url, error) {
				panel.clear();
				if (error) return panel.add(ui.Label(t('error') + error, {color: '#b00020'}));
				panel.add(ui.Label(t('csv') + ' ↓', {fontSize: '12px'}, url));
			});
		}));
		return panel;
	}

	// Pixel size of the percentiles of the colour ramp: about 250 000 pixels over the bounds of the region (1 to 10
	// km when they are of a large area: mo.defaultScale)
	function rangeScale(e) {
		return Math.max(Number(e.m), mo.defaultScale(e.m, state.info.boundsArea, 2.5e5));
	}

	// Map -----------------------------------------------------------------------------------------------------------

	// Why the map of the variable cannot have the true colour of its images (a key of T), or null if it can: a fixed
	// layer, a variable whose images have no red, green and blue bands (mo.rgbOf), a comparison of two periods (the map
	// is their difference) and the metrics that give no colours (sum, std, count, mode: mo.checkRgbMetric)
	function noRgbReason() {
		var e = entry();
		if (e.static) return 'rgbStatic';
		if (!mo.rgbOf(e)) return 'rgbNone';
		if (state.compareOn) return 'rgbCompare';
		try {
			mo.checkRgbMetric(state.mapMetric);
			if (state.temporal !== 'period') mo.checkRgbMetric(state.interannual);
		} catch (err) {
			return 'rgbMetric';
		}
		return null;
	}

	// The layer of the map chosen: 'index', 'rgb' (the true colour of its images) or 'both' (the true colour, and the
	// index on top of it); the index when there is no true colour (noRgbReason)
	function mapLayer() {
		return noRgbReason() ? 'index' : state.mapLayer;
	}

	function addMap() {
		var e = entry();
		computed(state.compareOn && !e.static ? 'compare_map' : mapLayer() === 'rgb' ? 'rgb_map' : 'map_layer');
		if (!ready(e)) return;
		var s = specOf(null, state.mapMetric);
		s.temporal = state.temporal;
		s.interannual = state.interannual;
		var geom = state.region.geometry();
		var layer = mapLayer();
		var img, name;
		if (e.static) {  // a fixed layer without dates (elevation, slope): no metric, period nor comparison
			var region = state.region;
			img = function (scale) { return mo.image(s, geom, scale).clipToCollection(region); };
			name = title(e);
			if (mo.isCategorical(e)) return addClassMap(e, img, name);  // class codes: a colour per class
		} else if (state.compareOn) {
			var o = specOf(state.other, state.mapMetric);
			o.temporal = s.temporal;
			o.interannual = s.interannual;
			img = mo.comparisonImage(s, o, geom).clipToCollection(state.region);
			name = title(e, [metricName(state.mapMetric), o.period.join('/') + ' − ' + s.period.join('/')]);
		} else {
			img = mo.image(s, geom).clipToCollection(state.region);
			name = title(e, [metricName(state.mapMetric), s.period.join('/')]);
		}
		// the true colour of the same images and pixels, with the same metric (services.rgb_map)
		var rgb = layer === 'index' ? null : mo.image(s, geom, null, true).clipToCollection(state.region);
		var rgbName = name + ' · ' + t('l_rgb');
		var id = start();
		var compare = state.compareOn && !e.static;
		var band = e.static ? img() : compare ? img.select('difference') : img;
		var scale = rangeScale(e);
		// the entry for the colour ramp: the range of a spread (standard deviation, coefficient of variation) is not
		// that of the variable (services.ramp_entry)
		var ramped = e.static ? e : mo.rampEntry(e, state.mapMetric, state.temporal, state.interannual);
		// the range of each layer in a request of its own (one that fails does not take the other with it), drawn when
		// both have come
		var st = {}, failed = {}, pending = 0;
		function got(what) {
			return function (value, error) {
				st[what] = value;
				failed[what] = Boolean(error);
				if (--pending === 0) draw();
			};
		}
		if (layer !== 'rgb') pending++;
		if (rgb) pending++;
		if (layer !== 'rgb') mo.percentiles(band, geom, scale).evaluate(got('index'));
		if (rgb) mo.rgbPercentiles(rgb, geom, scale).evaluate(got('rgb'));

		function draw() {
			if (id !== run) return;
			var widgets = [];
			var rvis = rgb ? mo.rgbVis(failed.rgb ? null : st.rgb) : null;  // 0 to 0.3 if they cannot be computed
			if (rgb) map.addLayer(rgb, rvis, rgbName);  // first, under the index (Both)
			if (layer !== 'rgb') {
				var stats = failed.index ? null : st.index;
				var vis;
				if (failed.index) {  // the range of the catalog (0 to 1 for the data outside it)
					var span = typeof ramped.minp === 'number' && typeof ramped.maxp === 'number' ?
						(ramped.maxp - ramped.minp) / 4 : 0.1;
					vis = compare ? {min: -span, max: span, palette: mo.DIVERGING} : mo.visParams(null, ramped);
				} else {
					vis = compare ? mo.trendVis('difference', stats.value_p5, stats.value_p95) : mo.visParams(stats, ramped);
				}
				map.addLayer(band, vis, name);
				var unit = unitText(e, state.mapMetric, state.temporal === 'period' ? null : state.interannual);
				colourBar(vis, name + (unit ? ' ' + unit : ''));
				widgets.push(ui.Label(name, {fontWeight: 'bold'}));
				if (failed.index) widgets.push(ui.Label(t(e.custom ? 'rangeNoteData' : 'rangeNote'), SMALL));
				widgets.push(downloadWidget(img, e, compare ? ['difference', 'reference', 'other'] : ['value'], name));
				if (compare) widgets.push(button(t('swipe'), function () { swipePeriods(img, e, ramped, s, o); }));
			}
			if (rgb) {
				rgbLegend(rvis, rgbName, layer === 'both');
				widgets.push(ui.Label(rgbName, {fontWeight: 'bold'}));
				widgets.push(ui.Label(rgbCaption(rvis), SMALL));
				if (failed.rgb) widgets.push(ui.Label(t('rgbRangeNote'), SMALL));
				widgets.push(downloadWidget(rgb, e, mo.RGB_BANDS, name, t('downloadRgb'), '_RGB'));
			}
			show(widgets);
		}
	}

	// The map of a categorical layer E (ECOREGION, BIOME; services.map_layer): the colour of each class, the legend of
	// the classes in the region (at most CLASSES_SHOWN, then how many more) and its GeoTIFF (IMG: a function of the pixel
	// size; the majority class on pixels more than twice as big as those of the data)
	var CLASSES_SHOWN = 25;

	function addClassMap(e, img, name) {
		var id = start();
		mo.classesIn(e, state.region.geometry()).evaluate(guardedAsync(id, function (ids) {
			var codes = mo.presentCodes(e, ids);
			map.addLayer(img(), mo.classVis(e, codes), name);
			var shown = mo.categoryLegend(e, codes, state.lang), cut = shown.slice(0, CLASSES_SHOWN);
			var more = shown.length > cut.length ? [fmt(t('moreClasses'), shown.length - cut.length)] : [];
			classLegend(name, cut.map(function (c) { return c.label; }).concat(more),
				cut.map(function (c) { return c.color.slice(1); }).concat(more.length ? ['ffffff'] : []));
			show([ui.Label(name, {fontWeight: 'bold'}), ui.Label(fmt(t('classesShown'), shown.length), SMALL),
				downloadWidget(img, e, ['value'], name)]);
		}));
	}

	// The swipe of a comparison (as the split maps of geemap): the reference period on the left and the other one on the
	// right, in two maps that move together, with the same colours (from the percentiles of both, those of a period
	// without pixels left out; the range of the catalog if neither has them) and their colour bar on the left map. The
	// legend of the map of the app (that of the difference) stays as it is; any other result, Close or Back to one map
	// show that map again (oneMap)
	function swipePeriods(img, e, ramped, s, o) {
		var geom = state.region.geometry();
		var both = img.select('reference').addBands(img.select('other'));
		var id = start();
		both.reduceRegion({reducer: ee.Reducer.percentile([5, 95]), geometry: geom, scale: rangeScale(e), bestEffort: true,
			maxPixels: 1e6, tileScale: 4}).evaluate(guardedAsync(id, function (st) {
			function numbers(values) {  // null for a period without pixels (Math.min would take it as 0)
				return values.filter(function (v) { return typeof v === 'number' && isFinite(v); });
			}
			var los = numbers([st.reference_p5, st.other_p5]), his = numbers([st.reference_p95, st.other_p95]);
			var vis = mo.visParams(los.length && his.length ?
				{value_p5: Math.min.apply(null, los), value_p95: Math.max.apply(null, his)} : null, ramped);
			var left = ui.Map(), right = ui.Map();
			[left, right].forEach(function (m) { m.setOptions('HYBRID'); m.setControlVisibility({layerList: false}); });
			left.addLayer(img.select('reference'), vis, s.period.join('/'));
			right.addLayer(img.select('other'), vis, o.period.join('/'));
			var key = ui.Panel({style: {position: 'bottom-left', padding: '6px 8px'}});
			var unit = unitText(e, s.metric, s.temporal === 'period' ? null : s.interannual);
			addColourBar(vis, title(e, [metricName(s.metric)]) + (unit ? ' ' + unit : ''), null, key);
			left.add(key);
			ui.Map.Linker([left, right]);
			left.centerObject(geom);
			var split = ui.SplitPanel({firstPanel: left, secondPanel: right, wipe: true, style: {stretch: 'both'}});
			show([ui.Label(t('swipe'), {fontWeight: 'bold'}),
				ui.Label(fmt(t('swipeNote'), s.period.join('/'), o.period.join('/')), SMALL),
				button(t('oneMap'), function () {
					oneMap();
					results.style().set('shown', false);
				})]);
			ui.root.widgets().set(1, split);  // after show, which puts the map of the app back
			swiped = true;
		}));
	}

	function mapWidgets() {
		var w = [header(t('map'))];
		var metrics = METRICS.map(function (m) { return {value: m, label: metricName(m)}; });
		w.push(row(ui.Label(t('metric')), metricSelect(state.mapMetric, function (v) {
			state.mapMetric = v;
			render();  // the true colour takes only some metrics (the Layer)
		})));
		var temporal = mo.TEMPORAL.map(function (x) { return {value: x, label: t('t_' + x)}; });
		var time = [row(ui.Label(t('temporal')), select(temporal, state.temporal, function (v) {
			state.temporal = v;
			render();
		}, '190px'))];
		if (state.temporal !== 'period') {
			time.push(row(ui.Label(t('interannual')), select(metrics, state.interannual, function (v) {
				state.interannual = v;
				render();
			})));
		}
		w = w.concat(entry().static ? disable(time) : time);  // a fixed layer: no aggregation in time
		// the index, the true colour of its images or both; greyed out, with the reason, when there is no true colour
		var why = noRgbReason();
		var layers = ['index', 'rgb', 'both'].map(function (x) { return {value: x, label: t('l_' + x)}; });
		var layer = select(layers, mapLayer(), function (v) {
			state.mapLayer = v;
			render();
		}, '190px');
		layer.setDisabled(Boolean(why));
		w.push(row(ui.Label(t('layer')), layer));
		if (why) w.push(ui.Label(t(why), SMALL));
		else if (state.mapLayer !== 'index') w.push(ui.Label(t('rgbNote'), SMALL));
		w.push(button(t('addMap'), guarded(addMap)));
		return w;
	}

	// Area by class (services.area_by_class) ------------------------------------------------------------------------

	// Hectares and % of each class over each feature of the region, of a land cover map of a year, of the variable cut
	// at the breaks (its map, as Map) or of its trend on each pixel (as Trends): a bar chart, a table and the CSV
	function areaByClass() {
		var kind = state.areaKind, regions = state.region, img, legend, extra = {}, name, native, colours;
		computed('area_by_class');
		if (!state.region || !state.info) return message(t('noRegion'), true);
		var geom = regions.geometry();
		if (kind === 'landcover' && state.areaChangeOn) return landcoverChanges();
		if (kind === 'landcover') {
			// as services.area_by_class: the land cover mask and where are for the classes of a variable
			if (state.landcoverOn || state.whereOn) return message(t('areaNoWhere'), true);
			var m = mo.landcoverMap(state.areaMap);
			var year = state.areaYear || mo.landcoverDefaultYear(m);
			img = mo.landcoverSource(m, year, geom).rename('class');
			legend = Object.keys(m.classes).map(Number).sort(function (a, b) { return a - b; }).map(function (code) {
				return [code, code + ' ' + m.names[String(code)], {landcover: m.classes[String(code)]}];
			});
			colours = legend.map(function (c) { return mo.LANDCOVER_COLOURS[c[2].landcover] || '9e9e9e'; });
			extra = {map: m.name, year: year};
			name = fmt(t('areaOf'), m.name + ' ' + year);
			native = Number(m.m);
		} else {
			var e = entry();
			if (!ready(e)) return;
			native = Number(e.m);
			if (kind === 'classes') {  // its own classes, on its pixels of the data (the legend: those with area)
				if (!mo.isCategorical(e)) return message(t('notCategorical'), true);
				img = mo.image(specOf(null, state.mapMetric), geom).rename('class');
				legend = null;
				name = fmt(t('areaOf'), title(e));
			} else if (kind === 'breaks') {
				if (mo.isCategorical(e)) {  // classes.mode_of: a categorical layer has its own classes
					return message('the classes of ' + e.index + ' (' + e.sensor + ') are its own (a categorical layer, ' +
						'of class codes): give no breaks', true);
				}
				var cuts = mo.checkBreaks(state.areaBreaks);
				var s = specOf(null, state.mapMetric);
				s.temporal = state.temporal;
				s.interannual = state.interannual;
				var unit = unitText(e, state.mapMetric, state.temporal === 'period' ? null : state.interannual)
					.replace(/^\[|\]$/g, '');
				img = mo.classifyBreaks(mo.image(s, geom), cuts);
				legend = mo.breakClasses(cuts, unit === 'unitless' ? '' : unit, state.lang).map(function (c) {
					return [c[0], c[1], {value_from: c[2], value_to: c[3]}];
				});
				var ramp = mo.ramp(e);
				colours = legend.map(function (c, i) { return ramp[Math.min(ramp.length - 1, Math.floor((i + 0.5) / legend.length * ramp.length))]; });
				name = title(e, [metricName(state.mapMetric)].concat(e.static ? [] : [s.period.join('/')]));
			} else {
				var ts = specOf(null, state.trendMetric);
				var part = state.trendStep === 'annual' ? 0 : state.trendPart;
				img = mo.classifyTrend(mo.trendImage(ts, geom, state.trendStep, part, state.trendMetric), 0.05);
				legend = mo.TREND_CLASSES.map(function (c) { return [c[0], state.lang === 'es' ? c[3] : c[1], {}]; });
				colours = mo.TREND_CLASSES.map(function (c) { return c[2]; });
				name = title(e, [t('trendMap'), ts.period.join('/')]);
			}
		}
		var scale = mo.areaScale(native, state.info.area);
		var id = start();
		mo.classHectares(img, regions, scale, state.info.crs).evaluate(guardedAsync(id, function (fc) {
			if (kind === 'classes') {  // the classes with area, with their colours (services.area_by_class)
				legend = mo.classAreaLegend(entry(), fc.features, state.lang);
				colours = legend.map(function (c) { return mo.categoryColour(entry(), c[0]); });
			}
			var rows = mo.areaRows(fc.features, legend, extra);
			var regionNames = regionsOf(rows);
			var shown = rows.filter(function (r) { return r.ha > 0; });
			var colour = {};
			legend.forEach(function (c, i) { colour[c[1]] = '#' + colours[i]; });
			var table = [[t('areaClass'), t('hectares'), {role: 'style'}]].concat(shown.map(function (r) {
				return [(regionNames.length > 1 ? r.region + ': ' : '') + r.label, r.ha, colour[r.label]];
			}));
			var group = kind === 'classes' ? mo.categoryGroupEntry(entry()) : null;  // the biome of each ecoregion
			var cols = ['region', 'class', 'label'].concat(kind === 'landcover' ? ['landcover'] :
				kind === 'breaks' ? ['value_from', 'value_to'] : group ? ['group', 'group_label'] : [])
				.concat(['ha', 'percent']);
			show([ui.Label(name, {fontWeight: 'bold'}),
				ui.Chart(table, 'BarChart', {legend: {position: 'none'}, hAxis: {title: t('hectares')}}),
				ui.Chart([[t('areaClass'), t('hectares'), t('areaPercent')]].concat(shown.map(function (r) {
					return [(regionNames.length > 1 ? r.region + ': ' : '') + r.label, num(r.ha, 4),
						r.percent === null ? '' : num(r.percent, 3)];
				})), 'Table'),
				ui.Label(fmt(t('areaNote'), num(scale)) + (kind === 'trend' ? ' ' + t('areaTrendNote') : ''), SMALL),
				csvWidget(rows, cols, name, kind === 'landcover' ? null : entry())].concat(group ? [
				ui.Chart([[t('areaClass'), t('hectares'), t('areaPercent')]].concat(
					mo.classGroupRows(fc.features, legend, group, state.lang).map(function (r) {
						return [(regionNames.length > 1 ? r.region + ': ' : '') + r.label, num(r.ha, 4),
							r.percent === null ? '' : num(r.percent, 3)];
					})), 'Table')] : []));
		}));
	}

	// The changes of the land cover map from its year to another: the hectares of each pair of broad land covers (each
	// pair of classes in the CSV), and the changed and unchanged area of each region
	function landcoverChanges() {
		var m = mo.landcoverMap(state.areaMap), regions = state.region, geom = regions.geometry();
		var year = state.areaYear || mo.landcoverDefaultYear(m), other = state.areaOther || mo.landcoverDefaultYear(m);
		if (year === other) return message(fmt(t('areaChanges'), m.name, year, other) + ': ' + t('badYears'), true);
		var img = mo.pairs(mo.landcoverSource(m, year, geom), mo.landcoverSource(m, other, geom));
		var scale = mo.areaScale(Number(m.m), state.info.area);
		var name = fmt(t('areaChanges'), m.name, year, other);
		var id = start();
		mo.classHectares(img, regions, scale, state.info.crs).evaluate(guardedAsync(id, function (fc) {
			var rows = mo.transitionRows(fc.features, m, year, other);
			var broad = mo.broadTransitions(rows, state.lang);
			var regionNames = regionsOf(rows);
			var notes = regionNames.map(function (g) {
				var ch = 0, un = 0;
				rows.forEach(function (r) {
					if (r.region !== g) return;
					if (r.from_class === r.to_class) un += r.ha; else ch += r.ha;
				});
				return ui.Label(fmt(t('areaChanged'), g, num(ch, 4), num(un, 4)));
			});
			show([ui.Label(name, {fontWeight: 'bold'})].concat(notes).concat([
				ui.Chart([[t('areaFrom'), t('areaTo'), t('hectares'), t('areaPercent')]].concat(broad.map(function (r) {
					return [(regionNames.length > 1 ? r.region + ': ' : '') + r.from_label, r.to_label, num(r.ha, 4),
						r.percent === null ? '' : num(r.percent, 3)];
				})), 'Table'),
				ui.Label(t('areaBroad') + ' ' + fmt(t('areaNote'), num(scale)), SMALL),
				csvWidget(rows, ['region', 'map', 'year', 'other_year', 'from_class', 'from_label', 'from_landcover',
					'to_class', 'to_label', 'to_landcover', 'ha', 'percent'], name, null)]));
		}));
	}

	function areaWidgets() {
		var w = [header(t('areas'))];
		var kinds = ['landcover', 'breaks', 'trend', 'classes'].map(function (k) { return {value: k, label: t('k_' + k)}; });
		w.push(row(ui.Label(t('areaKind')), select(kinds, state.areaKind, function (v) {
			state.areaKind = v;
			render();
		}, '230px')));
		if (state.areaKind === 'landcover') {
			var maps = mo.landcoverMaps().map(function (m) { return {value: m.key, label: m.name}; });
			var m = mo.landcoverMap(state.areaMap);
			var years = mo.landcoverYears(m).slice().reverse().map(function (y) { return {value: y, label: String(y)}; });
			if (!state.areaYear || mo.landcoverYears(m).indexOf(state.areaYear) < 0) state.areaYear = mo.landcoverDefaultYear(m);
			if (!state.areaOther || mo.landcoverYears(m).indexOf(state.areaOther) < 0) state.areaOther = mo.landcoverDefaultYear(m);
			if (state.areaChangeOn && state.areaYear === state.areaOther && years.length > 1) {
				// two different years (ticked, or another map): the first one, the year before the other, as in QGIS
				var i = years.map(function (y) { return y.value; }).indexOf(state.areaOther);
				state.areaYear = years[i + 1 < years.length ? i + 1 : i - 1].value;
			}
			w.push(row(ui.Label(t('areaMap')), select(maps, state.areaMap, function (v) {
				state.areaMap = v;
				state.areaYear = null;
				state.areaOther = null;
				render();
			}, '150px'), select(years, state.areaYear, function (v) { state.areaYear = v; }, '80px')));
			var other = select(years, state.areaOther, function (v) { state.areaOther = v; }, '80px');
			other.setDisabled(!state.areaChangeOn);
			w.push(row(check(t('areaChange'), state.areaChangeOn, function (v) {
				state.areaChangeOn = v;
				render();
			}), other));
			if (state.areaChangeOn && years.length < 2) w.push(ui.Label(fmt(t('areaOneYear'), m.name), SMALL));
		} else if (state.areaKind === 'breaks') {
			w.push(row(ui.Label(t('areaBreaks')), ui.Textbox({placeholder: t('breaksHint'), value: state.areaBreaks,
				onChange: function (v) { state.areaBreaks = v; }, style: {width: '190px'}})));
		} else if (state.areaKind === 'classes') {
			w.push(ui.Label(t('areaClassesNote'), SMALL));
		} else {
			w.push(ui.Label(t('areaTrendNote'), SMALL));
		}
		w.push(button(t('computeAreas'), guarded(areaByClass)));
		return (state.areaKind === 'trend' && entry().static) || (state.areaKind === 'breaks' && mo.isCategorical(entry())) ?
			disable(w) : w;
	}

	// Gradients (services.region_stats with zones, services.transect) ----------------------------------------------

	// The map of the variable, as Map (no metric for a fixed layer), and its spec
	function mapImage(geom) {
		var e = entry();
		var s = specOf(null, state.mapMetric);
		s.temporal = state.temporal;
		s.interannual = state.interannual;
		return {e: e, s: s, image: mo.image(s, geom), name: title(e, [metricName(state.mapMetric)].concat(
			e.static ? [] : [s.period.join('/')]))};
	}

	function zoneEntry() {
		var statics = mo.variables().filter(function (v) { return v.static; });
		if (!state.zoneRef) state.zoneRef = (statics.filter(function (v) { return v.index === 'ELEVATION'; })[0] || statics[0]).ref;
		return mo.byRef(state.zoneRef);
	}

	// The percentiles 25, 50 and 75 and the mean of the map in each band of a fixed layer (the elevation), over each
	// feature: a chart of the median of each band, a table and its CSV
	function zoneStatistics() {
		var e = entry();
		computed('region_stats');
		if (!ready(e)) return;
		if (mo.isCategorical(e)) return message(t('zoneNoCategorical'), true);
		var z = zoneEntry();
		if (mo.isCategorical(z)) return classZoneStatistics(e, z);  // its classes are the zones
		var cuts = mo.checkBreaks(state.zoneBreaks);
		var geom = state.region.geometry();
		var m = mapImage(geom);
		var scale = mo.autoScale(e, state.info.area);
		var zs = mo.spec({ref: z.ref, quality: state.quality});
		mo.used(zs);  // the data of the zones, under the result (services._zone_spec)
		var zone = mo.classifyBreaks(mo.image(zs, geom, scale), cuts);
		var unit = (z.unit || '').replace(/^\[|\]$/g, '');
		var legend = mo.breakClasses(cuts, unit === 'unitless' ? '' : unit, state.lang);
		var name = fmt(t('zoneTitle'), m.name, z.index);
		var id = start();
		mo.zoneStats(m.image, zone, state.region, scale, state.info.crs).evaluate(guardedAsync(id, function (fc) {
			var rows = mo.zoneRows(fc.features, legend);
			var regionNames = regionsOf(rows);
			var chart = [[t('zoneBand')].concat(regionNames)].concat(legend.map(function (l) {
				return [l[1]].concat(regionNames.map(function (g) {
					var r = rows.filter(function (x) { return x.region === g && x.zone === l[0]; })[0];
					return r && r.p50 !== null ? r.p50 : null;
				}));
			}));
			show([ui.Label(name, {fontWeight: 'bold'}),
				ui.Chart(chart, 'LineChart', {pointSize: 4, vAxis: {title: unitText(e, state.mapMetric,
					state.temporal === 'period' ? null : state.interannual)}}),
				ui.Chart([[t('zoneBand'), 'p25', 'p50', 'p75', metricName('mean')]].concat(rows.map(function (r) {
					return [(regionNames.length > 1 ? r.region + ': ' : '') + r.zone_label, num(r.p25), num(r.p50),
						num(r.p75), num(r.mean)];
				})), 'Table'),
				ui.Label(fmt(t('zoneNote'), num(scale)), SMALL),
				csvWidget(rows, ['region', 'zone', 'zone_label', 'zone_from', 'zone_to', 'p25', 'p50', 'p75', 'mean',
					'n_pixels'], name, e)]);
		}));
	}

	// The percentiles 25, 50 and 75 and the mean of the map in each class of the categorical layer Z (ECOREGION, BIOME)
	// with pixels in each feature (services.region_stats with zones {variable, sensor}, without breaks): a table and its
	// CSV
	function classZoneStatistics(e, z) {
		var geom = state.region.geometry();
		var m = mapImage(geom);
		var scale = mo.autoScale(e, state.info.area);
		var zs = mo.spec({ref: z.ref, quality: {}});
		mo.used(zs);  // the data of the zones, under the result (services._zone_spec)
		var zone = mo.classZone(zs, geom, scale);
		var name = fmt(t('zoneClassTitle'), m.name, z.index);
		var id = start();
		mo.zoneStats(m.image, zone, state.region, scale, state.info.crs).evaluate(guardedAsync(id, function (fc) {
			var rows = mo.classZoneRows(fc.features, z, state.lang);
			var regionNames = regionsOf(rows);
			show([ui.Label(name, {fontWeight: 'bold'}),
				ui.Chart([[t('areaClass'), 'p25', 'p50', 'p75', metricName('mean')]].concat(rows.map(function (r) {
					return [(regionNames.length > 1 ? r.region + ': ' : '') + r.zone_label, num(r.p25), num(r.p50),
						num(r.p75), num(r.mean)];
				})), 'Table'),
				ui.Label(fmt(t('zoneNote'), num(scale)), SMALL),
				csvWidget(rows, ['region', 'zone', 'zone_label', 'p25', 'p50', 'p75', 'mean', 'n_pixels'], name, e)]);
		}));
	}

	// The profile of the map along the LINE drawn, with the elevation: 100 segments (at least a pixel of the data)
	function profile(line) {
		var e = entry();
		computed('transect');
		if (e.problem) return message(e.problem, true);
		if (mo.isCategorical(e)) return message(t('profileCategorical'), true);
		var m = mapImage(line.buffer(1000));
		var native = Number(e.m);
		var elevation = mo.variables().filter(function (v) { return v.index === 'ELEVATION'; })[0];
		var demSpec = mo.spec({ref: elevation.ref, quality: {}});
		mo.used(demSpec);  // the elevation is on the chart too (services.transect)
		var dem = mo.image(demSpec, line.buffer(1000), 30);
		var id = start();
		ee.Dictionary({length: line.length(1), centroid: line.centroid(1).coordinates()}).evaluate(guardedAsync(id, function (d) {
			var step = Math.max(native, d.length / 100);
			var cuts = mo.transectCuts(d.length, step);
			var name = fmt(t('profileTitle'), m.name, num(d.length / 1000, 3));
			mo.transectStats(m.image, dem, line, cuts, native, mo.utmOf(d.centroid[0], d.centroid[1]))
				.evaluate(guardedAsync(id, function (fc) {
					var rows = mo.transectRows(fc.features, cuts, d.length);
					var chart = [[t('distance'), entry().index || 'value', t('elevationM')]].concat(rows.map(function (r) {
						return [r.distance_m / 1000, r.value, r.elevation];
					}));
					show([ui.Label(name, {fontWeight: 'bold'}),
						ui.Chart(chart, 'LineChart', {hAxis: {title: t('distance')}, series: {1: {targetAxisIndex: 1,
							color: '#9e9e9e'}}, vAxes: {0: {title: unitText(e, state.mapMetric,
							state.temporal === 'period' ? null : state.interannual)},
							1: {title: t('elevationM')}}}),
						ui.Label(fmt(t('profileNote'), num(step)), SMALL),
						csvWidget(rows, ['distance_m', 'value', 'elevation', 'lon', 'lat'], name, e)]);
				}));
		}));
	}

	function gradientWidgets() {
		var w = [header(t('gradients'))];
		var statics = mo.variables().filter(function (v) { return v.static; }).map(function (v) {
			return {value: v.ref, label: v.index + ' · ' + v.sensor};
		});
		zoneEntry();
		w.push(row(ui.Label(t('zonesOf')), select(statics, state.zoneRef, function (v) { state.zoneRef = v; }, '150px'),
			ui.Textbox({placeholder: t('breaksHint'), value: state.zoneBreaks,
				onChange: function (v) { state.zoneBreaks = v; }, style: {width: '120px'}})));
		w.push(button(t('zoneStats'), guarded(zoneStatistics)));
		w.push(button(t('drawLine'), function () {
			state.drawingLine = true;
			drawing.setShown(true);
			drawing.setDrawModes(['line', 'polygon']);
			drawing.setShape('line');
			message(t('drawLineHelp'));
		}));
		return w;
	}

	// Animation (services.timelapse) -------------------------------------------------------------------------------

	// The frames of the period, one per year, month or 16 days, each the metric of its images with the colours of the
	// map of the whole period (its percentiles 5 and 95, as services.timelapse; of the count, those of the median of
	// the frames: mo.animationRange), as a thumbnail that plays them, its dates and its colour bar; and the GIF to
	// download
	function timelapse() {
		var e = entry();
		computed('timelapse');
		if (!ready(e)) return;
		var s = specOf(null, state.animMetric);
		var step = state.animStep;
		var steps = mo.animationSteps(s, step);  // its errors before Earth Engine
		var geom = state.region.geometry();
		var region = state.region;
		var name = title(e, [metricName(state.animMetric), s.period.join('/')]);
		var ramped = mo.rampEntry(e, state.animMetric, 'period');
		var id = start();
		var range = mo.animationRange(s, region, steps, state.animMetric);
		mo.percentiles(range, geom, rangeScale(e)).evaluate(function (st, error) {
			if (id !== run) return;
			var vis = mo.visParams(error ? null : st, ramped);
			var frames = mo.animationFrames(s, region, steps, state.animMetric, vis);
			var params = {dimensions: 600, region: geom.bounds(1000), framesPerSecond: 1, crs: 'EPSG:3857'};
			var labels = steps.map(function (b) { return mo.frameLabel(step, b[0], b[1], state.lang); });
			var unit = unitText(e, state.animMetric, null);
			colourBar(vis, name + (unit ? ' ' + unit : ''));
			var gif = ui.Panel();
			gif.add(button(t('animGif'), function () {
				gif.clear();
				gif.add(ui.Label(t('computing'), SMALL));
				frames.getVideoThumbURL(params, function (url, err) {
					gif.clear();
					if (err) return gif.add(ui.Label(t('error') + err, {color: '#b00020'}));
					gif.add(ui.Label(t('animGif'), {fontSize: '12px'}, url));
				});
			}));
			// the time slider: a frame on the map, chosen with a slider (as the time sliders of geemap), cut to the
			// region: the white outside it (that of the thumbnail and the GIF) would hide the whole map
			var list = frames.toList(steps.length);
			var frameOf = function (i) { return ee.Image(list.get(i)).clipToCollection(region); };
			var frameLayer = ui.Map.Layer(frameOf(0), {}, labels[0]);
			map.layers().add(frameLayer);
			var current = ui.Label(labels[0], {fontSize: '12px'});
			var slider = ui.Slider({min: 0, max: steps.length - 1, step: 1, value: 0, style: {stretch: 'horizontal'},
				onChange: function (i) {
					frameLayer.setEeObject(frameOf(i));
					frameLayer.setName(labels[i]);
					current.setValue(labels[i]);
				}});
			show([ui.Label(name, {fontWeight: 'bold'}), ui.Thumbnail({image: frames, params: params}),
				ui.Label(fmt(t('animFrames'), steps.length, num(vis.min), num(vis.max), labels.join(', ')), SMALL),
				ui.Label(t('animNote'), SMALL), gif].concat(steps.length > 1 ?
				[ui.Label(t('animSlider'), {fontWeight: 'bold', fontSize: '12px'}), row(slider, current)] : []));
		});
	}

	function animationWidgets() {
		var w = [header(t('animation'))];
		var steps = mo.ANIMATION_STEPS.map(function (x) { return {value: x, label: t('a_' + x)}; });
		w.push(row(ui.Label(t('animStep')), select(steps, state.animStep, function (v) { state.animStep = v; })));
		w.push(row(ui.Label(t('animMetric')), metricSelect(state.animMetric, function (v) { state.animMetric = v; })));
		w.push(button(t('makeAnimation'), guarded(timelapse)));
		return entry().static ? disable(w) : w;  // a fixed layer without dates: no animation
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

	// The chart of the time series ROWS of the entry E: a line per region or, for the snow cover days (metric days, as
	// services.time_series gives bars), a bar per step from 0, those of the regions side by side
	function seriesChart(rows, e, name) {
		var bars = mo.isDays(state.stepMetric);
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
		var legend = {position: regions.length > 1 ? 'right' : 'none'};
		if (bars) {
			return ui.Chart({cols: cols, rows: data}, 'ColumnChart', {title: name,
				vAxis: {title: axisTitle(e, state.stepMetric, state.stat), viewWindow: {min: 0}}, legend: legend,
				bar: {groupWidth: '80%'}});
		}
		return ui.Chart({cols: cols, rows: data}, 'LineChart', {title: name,
			vAxis: {title: axisTitle(e, state.stepMetric, state.stat)}, lineWidth: 1.5,
			pointSize: 3, interpolateNulls: false, legend: legend});
	}

	// The table of the time series ROWS (that of the snow cover days, under their bars): region, date, value, images
	// and valid pixels of each step, as the CSV
	function seriesTable(rows) {
		return ui.Chart([[t('region'), t('date'), t('value'), t('nImages'), t('validPixels')]].concat(rows.map(function (r) {
			return [r.region, r.date, r.value === null ? '' : num(r.value, 4), r.n_images, r.n_pixels];
		})), 'Table');
	}

	// The colour at F (0 to 1) along the ramp COLOURS (hex), between its two nearest colours
	function rampColour(colours, f) {
		var x = Math.max(0, Math.min(1, f)) * (colours.length - 1), i = Math.min(Math.floor(x), colours.length - 2);
		return '#' + [0, 2, 4].map(function (j) {
			var a = parseInt(colours[i].substr(j, 2), 16), b = parseInt(colours[i + 1].substr(j, 2), 16);
			var c = Math.round(a + (b - a) * (x - i));
			return (c < 16 ? '0' : '') + c.toString(16);
		}).join('');
	}

	// The time series with a line per year over the days of the year (services.time_series with doy) of the feature
	// REGION (its rows with year and doy: see computeSeries), from the oldest year (light) to the newest (dark,
	// thicker), as charts.doy_png
	function doyChart(rows, e, name, region) {
		var years = [], values = {}, days = [];
		rows.forEach(function (r) {
			if (r.region !== region) return;
			if (years.indexOf(r.year) < 0) years.push(r.year);
			if (days.indexOf(r.doy) < 0) days.push(r.doy);
			values[r.year + '|' + r.doy] = r.value;
		});
		years.sort();
		days.sort(function (a, b) { return a - b; });
		var table = [[t('dayOfYear')].concat(years.map(String))].concat(days.map(function (d) {
			return [d].concat(years.map(function (y) {
				var v = values[y + '|' + d];
				return v === undefined ? null : v;
			}));
		}));
		var series = {};
		years.forEach(function (y, k) {
			var newest = k === years.length - 1;
			series[k] = {color: rampColour(mo.YEARS, 0.15 + 0.85 * k / Math.max(years.length - 1, 1)),
				lineWidth: newest ? 2.2 : 1, pointSize: newest ? 3 : 2};
		});
		return ui.Chart(table, 'LineChart', {title: name + ' · ' + region, interpolateNulls: true, series: series,
			hAxis: {title: t('dayOfYear'), viewWindow: {min: 1, max: 366}},
			vAxis: {title: axisTitle(e, state.stepMetric, state.stat)}});
	}

	var PROFILE_COLOURS = ['#1f77b4', '#d62728'];  // charts.PROFILE_COLOURS: the line of the left axis, of the right axis
	// the metrics between the years of the seasonal profile by day of the year, as in the QGIS plugin
	var BETWEEN = ['mean', 'median', 'min', 'max', 'p25', 'p75', 'std', 'cv'];

	// The name of the step of the year of the row R of a profile (its label, in English: 'Mar', 'Jan 17') in the language
	// of the app
	function stepName(r) {
		if (state.lang === 'en') return r.label;
		var p = r.label.split(' ');
		var month = mo.partLabel('monthly', mo.MONTH_ABBR.indexOf(p[0]) + 1, 'es');
		return p.length > 1 ? p[1] + ' ' + month.slice(0, 3) : month;
	}

	// The seasonal profile PROF (mo.doyProfile) of the feature REGION over the days of the year, a line per variable of
	// NAMES: the first on the left axis (blue), the other on the right axis (red), each axis (its title in TITLES) from
	// the minimum to the maximum of the values of its own variable and in the colour of its line when there are two, as
	// charts.doy_profile_png; titled NAME, and the feature when there are SEVERAL
	function profileChart(prof, names, titles, name, region, several) {
		var parts = [], values = {}, at = {};  // a point per step of the year (part), on its day: 29 February and 1 March
		prof.forEach(function (r) {
			if (r.region !== region) return;
			if (!at.hasOwnProperty(r.part)) {
				parts.push(r.part);
				at[r.part] = {doy: r.doy, label: stepName(r)};
			}
			values[r.variable + '|' + r.part] = r.value;
		});
		parts.sort(function (a, b) { return at[a].doy - at[b].doy || (a < b ? -1 : a > b ? 1 : 0); });
		var cols = [{id: 'doy', label: t('dayOfYear'), type: 'number'}].concat(names.map(function (n, k) {
			return {id: 'v' + k, label: n, type: 'number'};
		}));
		var data = parts.map(function (p) {
			return {c: [{v: at[p].doy, f: at[p].label}].concat(names.map(function (n) {
				var v = values[n + '|' + p];
				return {v: v === undefined ? null : v};
			}))};
		});
		var series = {}, vAxes = {};
		names.forEach(function (n, k) {
			var colour = PROFILE_COLOURS[k];
			series[k] = {targetAxisIndex: k, color: colour};
			vAxes[k] = {title: titles[k]};
			if (names.length > 1) vAxes[k].titleTextStyle = vAxes[k].textStyle = {color: colour};
		});
		return ui.Chart({cols: cols, rows: data}, 'LineChart', {title: name + (several ? ' · ' + region : ''),
			interpolateNulls: true, lineWidth: 1.6, pointSize: 4, series: series, vAxes: vAxes, legend: {position: 'bottom'},
			hAxis: {title: t('dayOfYear'), viewWindow: {min: 1, max: 366}, ticks: mo.MONTH_STARTS.map(function (d, i) {
				return {v: d, f: partName('monthly', i + 1)};
			})}});
	}

	// Whether the series by day of the year is its seasonal profile (services.time_series with doy and interannual or
	// other_variable), not a line per year
	function isProfile() {
		return state.doy && state.step !== 'annual' && (state.doyBetween !== 'years' || state.doyOther !== 'none');
	}

	// The pixel filters of the variable of the right axis OE of a profile: those of the panel, with those unchecked only
	// because the variable of the panel measures them back on (the snow of the NDSI, for the NDVI); with a variable of
	// fixed filters in the panel (SCF, CF, data by ID: its greyed out filters are not a choice), those the user chose
	// before selecting it, or else the defaults. Never that of what OE measures (as 'auto' does in services.time_series
	// and the QGIS plugin): the NDSI on the right axis keeps its snow
	function otherQuality(oe) {
		var e = entry();
		var fixed = e && mo.fixedFilters(e);
		var q = {cloud_score: state.quality.cloud_score};
		mo.FILTERS.forEach(function (f) {
			var on = fixed ? (state.chosenQuality ? state.chosenQuality[f] : true) :
				state.quality[f] || (e && (mo.MEASURES[f] || []).indexOf(e.index) >= 0);
			q[f] = Boolean(on) && (mo.MEASURES[f] || []).indexOf(oe.index) < 0;
		});
		return q;
	}

	// The spec of the variable of the right axis of a profile, computed as the variable of the panel of spec S: the same
	// period, season, pixel filters of the panel (otherQuality) and pixels of the region (where, the land cover mask),
	// with its own rules (the SCF and the CF only take the metric mean), as services._other_spec; null without it
	function otherSpec(s) {
		if (state.doyOther === 'none') return null;
		try {
			mo.spec({ref: state.doyOther, metric: state.stepMetric});  // its only metric (SCF, CF), before Earth Engine
			var o = mo.spec({ref: state.doyOther, period: s.period.slice(), season: s.season,
				quality: otherQuality(mo.byRef(state.doyOther)),
				metric: 'mean', where: whereArgs()});
			mo.checkDates(o, 'time series');
			mo.used(o);
			return o;
		} catch (err) {
			throw new Error(t('rightAxis') + ': ' + (err.message || String(err)));
		}
	}

	// The seasonal profile by day of the year of the variable of the panel (spec S of the entry E) and of the variable
	// of the right axis, if one is chosen, computed as the first one (services.time_series with doy, interannual and
	// other_variable): for each step of the year, the metric between the years of its values (mo.doyProfile), a line per
	// variable over the days of the year, each on its y axis (from the minimum to the maximum of its values); a
	// chart for each feature, and the CSV of the profile (its columns and those of how it was computed, as Python)
	function computeProfile(e, s) {
		var o = otherSpec(s);
		var oe = o ? mo.entryOf(o) : null;
		if (oe && !ready(oe)) return;
		var entries = [e].concat(oe ? [oe] : []);
		var names = entries.map(mo.entryName);
		if (oe && names[0] === names[1]) throw new Error(fmt(t('sameOther'), names[1]));
		var between = state.doyBetween === 'years' ? 'median' : state.doyBetween;  // a right axis: the median by default
		var step = state.step, metric = state.stepMetric, stat = state.stat;
		var name = title(e, [metricName(metric) + ' ' + t('s_' + step).toLowerCase(), metricName(stat).toLowerCase(),
			fmt(t('ofTheYears'), metricName(between).toLowerCase())], names.join(' ' + t('and') + ' '));
		var id = start();
		function fetch(spec, done) {  // the days with images of each variable, daily
			if (step !== 'daily') return fetchSeries(spec, metric, mo.seriesBins(spec, step), id, done);
			mo.dailyDays(spec, state.region.geometry()).evaluate(guardedAsync(id, function (days) {
				fetchSeries(spec, metric, mo.dailyBins(days), id, done);
			}));
		}
		function draw(parts, scales) {
			var rows = [];
			parts.forEach(function (p, k) {
				mo.withDoy(p).forEach(function (r) {
					r.variable = names[k];
					rows.push(r);
				});
			});
			if (!rows.some(function (r) { return r.value !== null; })) return noData();
			var prof = mo.doyProfile(rows, s, step, between, names[0]);
			var titles = entries.map(function (x) { return axisTitle(x, metric, stat, between); });
			prof.forEach(function (r) {  // as the CSV of services.time_series: the sensor, unit and pixel size of each
				var k = names.indexOf(r.variable);
				r.sensor = entries[k].custom ? '' : entries[k].sensor;
				r.step = step;
				r.metric = metric;
				r.stat = stat;
				r.interannual = between;
				r.unit = mo.udunits(mo.unitOf(entries[k], metric, between, stat));
				r.scale_m = scales[k];
			});
			var note = names.length > 1 ? fmt(t('scalesNote'), num(scales[0]), names[0], num(scales[1]), names[1]) :
				fmt(t('scaleNote'), num(scales[0]));
			var regions = regionsOf(prof);
			show(regions.map(function (g) {  // each feature
				return profileChart(prof, names, titles, name, g, regions.length > 1);
			}).concat([
				ui.Label(fmt(t('doyNote'), metricName(between).toLowerCase()), SMALL),
				ui.Label(note + ' ' + t('chartHelp'), SMALL),
				csvWidget(prof, mo.PROFILE_COLUMNS.concat(mo.PROFILE_META), name, e)]));
		}
		function safely(f) {  // the errors of what runs after an answer of Earth Engine, in the results panel
			return function (rows, scale) {
				try {
					f(rows, scale);
				} catch (err) {
					message(err.message || String(err), true);
				}
			};
		}
		fetch(s, safely(function (rows, scale) {
			if (!o) return draw([rows], [scale]);
			fetch(o, safely(function (other, otherScale) { draw([rows, other], [scale, otherScale]); }));
		}));
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
		computed(state.compareOn ? 'compare_series' : 'time_series');
		if (!ready(e)) return;
		if (state.compareOn) return compareSeries();
		var s = specOf();
		if (isProfile()) return computeProfile(e, s);
		var name = title(e, [metricName(state.stepMetric) + ' ' + t('s_' + state.step).toLowerCase(),
			metricName(state.stat).toLowerCase()]);
		var id = start();
		function go(steps) {
			fetchSeries(s, state.stepMetric, steps, id, function (rows, scale) {
				if (!rows.some(function (r) { return r.value !== null; })) return noData();
				var doy = state.doy && state.step !== 'annual';  // a line per year: not with a value per year
				if (doy) mo.withDoy(rows);  // the year and the day of the year of each step
				var columns = ['region', 'date', 'value', 'n_pixels', 'n_images'].concat(doy ? ['year', 'doy'] : []);
				var bars = !doy && mo.isDays(state.stepMetric);  // the snow cover days: bars, and their table
				show((doy ? regionsOf(rows).map(function (g) { return doyChart(rows, e, name, g); }) :  // each feature
					[seriesChart(rows, e, name)]).concat(bars ? [seriesTable(rows)] : [],
					bars && state.step === 'daily' ? [ui.Label(t('scdDailyNote'), SMALL)] : [], [
					ui.Label(fmt(t('scaleNote'), num(scale)) + ' ' + t('chartHelp'), SMALL),
					csvWidget(rows, columns, name, e)]));
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
				var chart = ui.Chart({cols: cols, rows: data}, 'LineChart', {title: name,
					vAxis: {title: axisTitle(e, state.stepMetric, state.stat)},
					pointSize: 4, lineWidth: 1.5, series: series});
				show([chart, ui.Label(fmt(t('scaleNote'), num(scale)), SMALL), csvWidget(prof,
					['region', 'key', 'label', 'reference', 'other', 'difference', 'n_reference', 'n_other'], name, e)]);
			});
		});
	}

	function seriesWidgets() {
		var w = [header(t('series'))];
		var steps = mo.STEPS.map(function (x) { return {value: x, label: t('s_' + x)}; });
		w.push(row(ui.Label(t('step')), select(steps, state.step, function (v) { state.step = v; })));
		w.push(row(ui.Label(t('stepMetric')), metricSelect(state.stepMetric, function (v) { state.stepMetric = v; })));
		var stats = STATS.map(function (m) { return {value: m, label: metricName(m)}; });
		w.push(row(ui.Label(t('stat')), select(stats, state.stat, function (v) { state.stat = v; })));
		w.push(check(t('doy'), state.doy, function (v) {
			state.doy = v;
			render();
		}));
		if (state.doy) w = w.concat(doyWidgets());
		w.push(button(t('computeSeries'), guarded(computeSeries)));
		return entry().static ? disable(w) : w;  // a fixed layer without dates: no time series
	}

	// The options of the series by day of the year: the metric between the years of its seasonal profile (or a line per
	// year) and the variable of the right axis (one of the catalog with dates). A line per year is of one variable: a
	// variable on the right axis takes the median of the years, and a line per year leaves that variable out
	function doyWidgets() {
		var between = [{value: 'years', label: t('doyLines')}].concat(BETWEEN.map(function (m) {
			return {value: m, label: metricName(m)};
		}));
		var others = [{value: 'none', label: t('noOther')}].concat(variableItems().filter(function (i) {
			return !mo.byRef(i.value).static;
		}));
		var w = [row(ui.Label(t('interannual')), select(between, state.doyBetween, function (v) {
			state.doyBetween = v;
			if (v === 'years') state.doyOther = 'none';
			render();
		})), ui.Label(t('doyOther')), select(others, state.doyOther, function (v) {
			state.doyOther = v;
			if (v !== 'none' && state.doyBetween === 'years') state.doyBetween = 'median';
			render();
		}, '340px')];  // the right axis never with the filter of what it measures (otherQuality): no conflict to note
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
			mo.partLabel(step, part, state.lang), vAxis: {title: axisTitle(e, state.trendMetric, state.stat)},
			hAxis: {format: '####'}, series: series,
			legend: {position: regions.length > 1 ? 'right' : 'none'}});
	}

	function trendTable() {
		var e = entry();
		computed('trend_table');
		if (!ready(e)) return;
		var s = specOf();
		enoughYears(s);
		var step = state.trendStep;
		var first = mo.windows(s.period, s.season)[0][0];
		var name = title(e, [t('trends'), metricName(state.trendMetric).toLowerCase()]);
		var id = start();
		seasonalSeries(s, step, state.trendMetric, id, function (yearly, scale) {
			var rows = mo.trendRows(yearly, step, first, state.lang);
			var unit = unitText(e, state.trendMetric, null, state.stat);
			var cols = [t('part'), 'n', 'τ', 'Z', 'p', t('significantShort'), unit ? 'Sen (' + unit + '/' +
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
				'intercept', 'first_year', 'last_year'], name, e));
			show(widgets);
			showPart(parts[0]);
		});
	}

	function trendMap() {
		var e = entry();
		computed('trend_map');
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
		var value = unitText(e, state.trendMetric);
		var unit = output === 'slope' ? (value ? value + ' / ' + (state.lang === 'es' ? 'año' : 'year') : '') :
			output === 'intercept' ? value : '';
		var id = start();
		function add(vis) {
			map.addLayer(band, vis, name);
			colourBar(vis, name + (unit ? ' ' + unit : ''));
			show([ui.Label(name, {fontWeight: 'bold'}), downloadWidget(img, e, mo.OUTPUTS, name)]);
		}
		var fixed = mo.trendVis(output);
		if (fixed && output !== 'slope' && output !== 'z' && output !== 'n') return add(fixed);
		mo.percentiles(band, geom, rangeScale(e)).evaluate(guardedAsync(id, function (stats) {
			var auto = mo.visParams(stats, mo.rampEntry(e, state.trendMetric));
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
		w.push(row(ui.Label(t('yearMetric')), metricSelect(state.trendMetric, function (v) { state.trendMetric = v; })));
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
		return entry().static ? disable(w) : w;  // a fixed layer without dates: no trends
	}

	// Burn severity -------------------------------------------------------------------------------------------------

	// RBR: a continuous map of red (burned) to green (regrowth), its statistics over each region and its GeoTIFF
	function burnRatio() {
		var ref = state.fireSensor === 'Landsat' ? 104 : 103;
		var e = mo.byRef(ref);
		if (!ready(e)) return;
		checkPeriod(state.fireBefore);
		checkPeriod(state.fireAfter);
		var before = mo.spec({ref: ref, period: state.fireBefore.slice(), metric: 'median', quality: state.quality,
			where: whereArgs(state.fireBefore)});
		var after = mo.spec({ref: ref, period: state.fireAfter.slice(), metric: 'median', quality: state.quality,
			where: whereArgs(state.fireBefore)});
		var scale = Number(e.m);
		mo.used(before);
		mo.used(after);
		var out = mo.burnRatio(before, after, state.region, scale, state.info.crs);
		var name = title(e, ['RBR', before.period.join('/') + ' → ' + after.period.join('/')]);
		var vis = {min: -0.5, max: 0.5, palette: mo.DIVERGING.slice().reverse()};
		map.addLayer(out.image.select('rbr'), vis, name);
		colourBar(vis, name);
		var id = start();
		out.stats.evaluate(guardedAsync(id, function (fc) {
			var rows = mo.rbrTable(fc.features);
			var stats = ['mean', 'median', 'std', 'cv', 'p10', 'p90', 'min', 'max'];
			var table = [[t('region')].concat(stats.map(metricName), [t('hectares')])].concat(rows.map(function (r) {
				return [r.region].concat(stats.map(function (k) { return r[k] === null ? '' : num(r[k], 3); }),
					[num(r.ha, 4)]);
			}));
			show([ui.Label(name, {fontWeight: 'bold'}), ui.Label(t('rbrNote'), SMALL), ui.Chart(table, 'Table'),
				ui.Label(fmt(t('scaleNote'), num(scale)), SMALL), csvWidget(rows, mo.RBR_COLUMNS, name),
				downloadWidget(out.image, e, ['rbr', 'dnbr', 'nbr_before', 'nbr_after'], name),
				perimeterWidget(out.image.select('rbr'), 'RBR', scale, e, name, before, after)]);
		}));
	}

	// The perimeter of the burned area (services.burn_severity with perimeter: mo.burnPerimeter) of the burn index
	// INDEX, whose image is VALUE, of pixels of SCALE m: the value from which a pixel is burned (empty: that of its
	// classes; the RBR has none) and the smallest patch and island (ha); its polygons on the map, their hectares, their
	// download (GeoJSON or KML, with the fields of the file of the package) and the button to make them the region of
	// the next analyses. E: the entry; NAME: the name of the result; BEFORE and AFTER: the specs of the periods
	function perimeterWidget(value, index, scale, e, name, before, after) {
		var panel = ui.Panel();
		var out = ui.Panel();
		var classes = mo.CLASSES[index];
		// the value of the classes as fire.CLASSES writes it (dNBR 0.1, not 0.1000), with the decimal comma in Spanish
		var hint = classes ? String(classes.burned).replace('.', state.lang === 'es' ? ',' : '.') : '';
		var low = ui.Textbox({placeholder: classes ? index + ' ' + hint : 'RBR', style: {width: '80px'}});
		var smallest = ui.Textbox({value: num(mo.PERIMETER_MIN_HA), style: {width: '50px'}});
		panel.add(ui.Label(t('perimeter'), {fontWeight: 'bold', fontSize: '12px', margin: '10px 8px 0 8px'}));
		panel.add(ui.Label(t('perimeterHelp'), SMALL));
		panel.add(row(ui.Label(t('burnedFrom'), SMALL), low, ui.Label(t('smallest'), SMALL), smallest,
			ui.Label('ha', SMALL)));
		panel.add(button(t('perimeterButton'), function () {
			out.clear();
			var threshold, minHa;
			try {
				var given = String(low.getValue() || '').trim().replace(',', '.');
				threshold = mo.burnedMin(index, given === '' ? null : given);
				minHa = Number(String(smallest.getValue() || '').trim().replace(',', '.') || mo.PERIMETER_MIN_HA);
				if (isNaN(threshold) || isNaN(minHa) || minHa < 0) throw new Error(t('perimeterNumbers'));
			} catch (err) {
				return out.add(ui.Label(err.message || String(err), {color: '#b00020'}));
			}
			out.add(ui.Label(t('computing'), SMALL));
			var regionName = state.regionName;  // that of the severity, whatever the region is when it is used
			mo.burnPerimeter(value, threshold, state.region, scale, state.info.crs, minHa).evaluate(function (fc, error) {
				out.clear();
				if (error) return out.add(ui.Label(t('error') + error, {color: '#b00020'}));
				var found = fc.features.filter(function (f) { return f.properties.ha > 0; });
				if (!found.length) return out.add(ui.Label(fmt(t('noBurned'), index, num(threshold)), SMALL));
				// the polygons as they came, without computing them again in each use (fire.PERIMETER_FIELDS)
				var polygons = ee.FeatureCollection(found.map(function (f) {
					var p = f.properties;
					return ee.Feature(ee.Geometry(f.geometry, null, false), {name: t('burnedArea') + ' · ' + p.name,
						region: String(p.name), ha: p.ha, patches: p.patches, index: index, burned_min: threshold,
						min_ha: minHa, sensor: e.sensor, before: before.period.join('/'), after: after.period.join('/')});
				}));
				map.addLayer(polygons.style({color: '000000', fillColor: '00000000', width: 2}), {},
					name + ' · ' + t('perimeterLayer'));
				found.forEach(function (f) {
					out.add(ui.Label((found.length > 1 ? f.properties.name + ': ' : '') +
						fmt(t('perimeterHa'), num(f.properties.ha, 5), f.properties.patches), {fontSize: '12px'}));
				});
				// with .geo: without it, Earth Engine writes the GeoJSON without the polygons (the KML has them anyway)
				var fields = ['region', 'ha', 'patches', 'index', 'burned_min', 'min_ha', 'sensor', 'before', 'after',
					'.geo'];
				var links = ui.Panel([], ui.Panel.Layout.flow('horizontal'));
				out.add(links);
				[['geojson', 'geojson'], ['kml', 'kml']].forEach(function (k) {
					polygons.getDownloadURL(k[0], fields, fileName(name, e, '_perimeter'), function (url, err) {
						if (url) links.add(ui.Label(t(k[1]) + ' ↓', {fontSize: '12px'}, url));
						else if (err) links.add(ui.Label(t('error') + err, {color: '#b00020', fontSize: '12px'}));
					});
				});
				out.add(button(t('useRegion'), function () {
					// in the parameters, the polygons as GeoJSON (the package names each by its name, areas.region)
					setRegion(polygons, t('burnedArea') + ' · ' + regionName, {geojson: {type: 'FeatureCollection',
						features: found.map(function (f) {
							return {type: 'Feature', geometry: f.geometry,
								properties: {name: t('burnedArea') + ' · ' + f.properties.name}};
						})}});
				}));
			});
		}));
		panel.add(out);
		return panel;
	}

	// The references of the RdNBR shown with its results, as catalog.json cites them (methods.rdnbr: miller2007 and
	// howe2022; with MODIS also veraverbeke2010, the NBR of its bands 2 and 7): [citation, DOI, only with MODIS]
	var RDNBR_REFERENCES = [
		['Miller, J. D., & Thode, A. E. (2007). Quantifying burn severity in a heterogeneous landscape with a relative ' +
			'version of the delta Normalized Burn Ratio (dNBR). Remote Sensing of Environment, 109(1), 66–80.',
			'10.1016/j.rse.2006.12.006', false],
		['Howe, A. A., Parks, S. A., Harvey, B. J., Saberi, S. J., Lutz, J. A., & Yocom, L. L. (2022). Comparing ' +
			'Sentinel-2 and Landsat 8 for burn severity mapping in Western North America. Remote Sensing, 14(20), 5249.',
			'10.3390/rs14205249', false],
		['Veraverbeke, S., Lhermitte, S., Verstraeten, W. W., & Goossens, R. (2010). The temporal dimension of ' +
			'differenced Normalized Burn Ratio (dNBR) fire/burn severity studies: The case of the large 2007 Peloponnese ' +
			'wildfires in Greece. Remote Sensing of Environment, 114(11), 2548–2563.', '10.1016/j.rse.2010.05.029', true]
	];

	// The entry of the catalog of the burn severity chosen (mo.burnEntry): that of its index and of its sensor or, for
	// MODIS (only the RdNBR), of its collection, Terra or Aqua
	function fireEntry() {
		var modis = mo.RDNBR_MODIS.indexOf(state.fireSensor) >= 0;
		return mo.burnEntry(state.fireIndex, modis ? 'Modis' : state.fireSensor, modis ? state.fireSensor : null);
	}

	// RdNBR (Miller & Thode 2007): its classes on the map, with their legend, and the continuous RdNBR under them (from
	// red, burned, to green, regrowth: shown from the list of layers); the hectares of each class and the changed area
	// of each region, the statistics of the RdNBR, its references, the CSV of the classes and the GeoTIFF
	function burnRelative() {
		var e = fireEntry();
		if (!ready(e)) return;
		checkPeriod(state.fireBefore);
		checkPeriod(state.fireAfter);
		var before = mo.spec({ref: e.ref, period: state.fireBefore.slice(), metric: 'median', quality: state.quality,
			where: whereArgs(state.fireBefore)});
		var after = mo.spec({ref: e.ref, period: state.fireAfter.slice(), metric: 'median', quality: state.quality,
			where: whereArgs(state.fireBefore)});
		var scale = Number(e.m);
		mo.used(before);
		mo.used(after);
		var modis = e.sensor === 'Modis';
		var out = mo.burnSeverity(before, after, state.region, scale, state.info.crs, 'RdNBR');
		var periods = before.period.join('/') + ' → ' + after.period.join('/');
		var name = title(e, modis ? [e.col.split('/').pop(), periods] : [periods]);  // MOD09GA (Terra), MYD09GA (Aqua)
		var vis = {min: mo.RDNBR_RANGE[0], max: mo.RDNBR_RANGE[1], palette: mo.DIVERGING.slice().reverse()};
		map.addLayer(out.image.select('rdnbr'), vis, name, false);
		map.addLayer(out.image.select('severity'), {min: 0, max: 3, palette: mo.RDNBR_COLOURS},
			name + ' · ' + t('severityClasses'));
		classLegend(t('rdnbrLegend'), mo.severityLegend('RdNBR', state.lang).map(function (c) {
			return mo.classLabel(c, state.lang);
		}), mo.RDNBR_COLOURS);
		addColourBar(vis, t('rdnbrBar'), '8px 0 4px 0');
		var id = start();
		// one evaluate for each collection: in an ee.Dictionary, a FeatureCollection comes back without its features
		out.hectares.evaluate(guardedAsync(id, function (hectares) { out.stats.evaluate(guardedAsync(id, function (st) {
			var d = {hectares: hectares, stats: st};
			var rows = [];
			d.hectares.features.forEach(function (f) {
				rows = rows.concat(mo.severityTable(f.properties.groups, String(f.properties.name), state.lang, 'RdNBR'));
			});
			var changed = mo.burnedHa(rows);
			var regions = regionsOf(rows);
			var areas = regions.length > 1 ? regions.map(function (r) {
				return ui.Label(r + ': ' + fmt(t('changed'), num(changed[r], 4)));
			}) : [ui.Label(fmt(t('changed'), num(changed[regions[0]] || 0, 4)))];
			function limit(x) {  // the limits of the classes as fire.class_label writes them: 0.069, not 0.06900
				var s = String(Number(Number(x).toPrecision(4)));
				return state.lang === 'es' ? s.replace('.', ',') : s;
			}
			var table = [[t('klass'), 'RdNBR', t('hectares')]].concat(rows.map(function (r) {
				var range = (r.rdnbr_min === null ? '< ' + limit(r.rdnbr_max) : r.rdnbr_max === null ?
					'≥ ' + limit(r.rdnbr_min) : limit(r.rdnbr_min) + ' – ' + limit(r.rdnbr_max));
				return [(regions.length > 1 ? r.region + ': ' : '') + r.label, range, num(r.ha, 4)];
			}));
			var stats = ['mean', 'median', 'std', 'cv', 'p10', 'p90', 'min', 'max'];
			var statsRows = mo.rdnbrTable(d.stats.features);
			var statsTable = [[t('region')].concat(stats.map(metricName), [t('hectares')])].concat(statsRows.map(
				function (r) {
					return [r.region].concat(stats.map(function (k) {
						return r[k] === null || r[k] === undefined ? '' : num(r[k], 3);
					}), [num(r.ha, 4)]);
				}));
			var refs = [ui.Label(t('references'), {fontSize: '12px', fontWeight: 'bold'})].concat(
				RDNBR_REFERENCES.filter(function (r) { return modis || !r[2]; }).map(function (r) {
					return ui.Label(r[0] + ' https://doi.org/' + r[1], SMALL, 'https://doi.org/' + r[1]);
				}));
			show([ui.Label(name, {fontWeight: 'bold'})].concat(areas, [ui.Chart(table, 'Table'),
				ui.Chart(statsTable, 'Table'), ui.Label(t('rdnbrNote'), SMALL)], modis ? [ui.Label(t('modisNote'), SMALL)] :
				[], refs, [ui.Label(fmt(t('scaleNote'), num(scale)), SMALL), csvWidget(rows, mo.RDNBR_COLUMNS, name),
				downloadWidget(out.image, e, ['rdnbr', 'severity', 'dnbr', 'nbr_before', 'nbr_after'], name),
				perimeterWidget(out.image.select('rdnbr'), 'RdNBR', scale, e, name, before, after)]));
		})); }));
	}

	function burn() {
		computed('burn_severity');
		if (state.fireIndex === 'RBR') return burnRatio();
		if (state.fireIndex === 'RdNBR') return burnRelative();
		var ref = state.fireSensor === 'Landsat' ? 101 : 102;
		var e = mo.byRef(ref);
		if (!ready(e)) return;
		checkPeriod(state.fireBefore);
		checkPeriod(state.fireAfter);
		var before = mo.spec({ref: ref, period: state.fireBefore.slice(), metric: 'median', quality: state.quality,
			where: whereArgs(state.fireBefore)});
		var after = mo.spec({ref: ref, period: state.fireAfter.slice(), metric: 'median', quality: state.quality,
			where: whereArgs(state.fireBefore)});
		var scale = Number(e.m);
		mo.used(before);
		mo.used(after);
		var out = mo.burnSeverity(before, after, state.region, scale, state.info.crs);
		var names = mo.SEVERITY.map(function (c) { return state.lang === 'en' ? c[3] : c[2]; });
		var name = title(e, [t('dnbr'), before.period.join('/') + ' → ' + after.period.join('/')]);
		map.addLayer(out.image.select('severity'), {min: -2, max: 4, palette: mo.SEVERITY_COLOURS}, name);
		classLegend(t('dnbrLegend'), names, mo.SEVERITY_COLOURS);
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
				downloadWidget(out.image, e, ['dnbr', 'severity', 'nbr_before', 'nbr_after'], name),
				perimeterWidget(out.image.select('dnbr'), 'dNBR', scale, e, name, before, after)]);
		}));
	}

	// The burn severity: first the index, as its sensors depend on it (mo.BURN_SENSORS: MODIS Terra and Aqua only for
	// the RdNBR), then the sensor and the periods before and after the fire
	function fireWidgets() {
		var w = [header(t('fire'))];
		var rdnbr = state.fireIndex === 'RdNBR';
		var modis = mo.RDNBR_MODIS.indexOf(state.fireSensor) >= 0;
		w.push(row(ui.Label(t('index')), select(mo.BURN_INDICES.map(function (i) {
			return {value: i, label: t('idx_' + i)};
		}), state.fireIndex, function (v) {
			state.fireIndex = v;
			// MODIS only with the RdNBR: Landsat, as big regions
			if (v !== 'RdNBR' && mo.RDNBR_MODIS.indexOf(state.fireSensor) >= 0) state.fireSensor = 'Landsat';
			render();
		}, '260px')));
		var sensors = [{value: 'Sentinel-2', label: 'Sentinel-2 (10 m)'}, {value: 'Landsat', label: 'Landsat (30 m)'}];
		if (rdnbr) {
			sensors = sensors.concat([{value: mo.RDNBR_MODIS[0], label: 'MODIS Terra (500 m)'},
				{value: mo.RDNBR_MODIS[1], label: 'MODIS Aqua (500 m)'}]);
		}
		w.push(row(ui.Label(t('sensor')), select(sensors, state.fireSensor, function (v) {
			state.fireSensor = v;
			if (rdnbr) render();  // the note of MODIS
		})));
		if (rdnbr) w.push(ui.Label(t('rdnbrHint'), SMALL));
		if (rdnbr && modis) w.push(ui.Label(t('modisNote'), SMALL));
		w.push(ui.Label(t('before'), {margin: '4px 8px 0 8px'}));
		w.push(row(box(state.fireBefore[0], function (v) { state.fireBefore[0] = v.trim(); }), ui.Label(t('to')),
			box(state.fireBefore[1], function (v) { state.fireBefore[1] = v.trim(); })));
		w.push(ui.Label(t('after'), {margin: '4px 8px 0 8px'}));
		w.push(row(box(state.fireAfter[0], function (v) { state.fireAfter[0] = v.trim(); }), ui.Label(t('to')),
			box(state.fireAfter[1], function (v) { state.fireAfter[1] = v.trim(); })));
		w.push(button(t('burn'), guarded(burn)));
		return w;
	}

	// Parameters of the analysis as JSON (monitoreo.parameters) ----------------------------------------------------

	// The analyses of the app as the functions of monitoreo.services that compute the same (parameters.ANALYSES): the
	// group of the panel and the button that compute each one, the parameters it takes, with the names of the services
	// (the other parameters of the services are not options of the app), and the values of those not given (the
	// defaults of the arguments of the services)
	var SOURCE = ['variable', 'sensor', 'collection', 'ref', 'image', 'band', 'band_reducer', 'band_scale', 'band_offset',
		'unit'];
	var PIXELS = ['start', 'end', 'season', 'quality', 'where'];
	var MAP_OPTIONS = ['metric', 'temporal', 'interannual'];
	var MAP_DEFAULTS = {metric: 'median', temporal: 'period', interannual: 'mean'};
	var ANALYSES = {
		map_layer: {group: 'map', button: 'addMap', takes: ['region'].concat(SOURCE, PIXELS, MAP_OPTIONS),
			defaults: MAP_DEFAULTS},
		rgb_map: {group: 'map', button: 'addMap', takes: ['region'].concat(SOURCE, PIXELS, MAP_OPTIONS),
			defaults: MAP_DEFAULTS},
		compare_map: {group: 'map', button: 'addMap',
			takes: ['region', 'other_start', 'other_end'].concat(SOURCE, PIXELS, MAP_OPTIONS), defaults: MAP_DEFAULTS},
		area_by_class: {group: 'areas', button: 'computeAreas',
			takes: ['region', 'landcover', 'year', 'other_year', 'breaks', 'trend', 'step', 'part', 'alpha'].concat(SOURCE,
				PIXELS, MAP_OPTIONS),
			defaults: {temporal: 'period', interannual: 'mean', step: 'annual', alpha: 0.05}},
		region_stats: {group: 'gradients', button: 'zoneStats', takes: ['region', 'zones'].concat(SOURCE, PIXELS,
			MAP_OPTIONS), defaults: MAP_DEFAULTS},
		transect: {group: 'gradients', button: 'drawLine', takes: ['line'].concat(SOURCE, PIXELS, MAP_OPTIONS),
			defaults: MAP_DEFAULTS},
		timelapse: {group: 'animation', button: 'makeAnimation', takes: ['region', 'step', 'metric'].concat(SOURCE, PIXELS),
			defaults: {step: 'annual', metric: 'median'}},
		time_series: {group: 'series', button: 'computeSeries',
			takes: ['region', 'step', 'metric', 'stat', 'doy', 'interannual', 'other_variable', 'other_sensor'].concat(
				SOURCE, PIXELS), defaults: {step: 'monthly', metric: 'mean', stat: 'mean'}},
		compare_series: {group: 'series', button: 'computeSeries',
			takes: ['region', 'other_start', 'other_end', 'step', 'metric', 'stat'].concat(SOURCE, PIXELS),
			defaults: {step: 'monthly', metric: 'mean', stat: 'mean'}},
		trend_table: {group: 'trends', button: 'trendTable',
			takes: ['region', 'step', 'metric', 'stat', 'alpha'].concat(SOURCE, PIXELS),
			defaults: {step: 'annual', metric: 'mean', stat: 'mean', alpha: 0.05}},
		trend_map: {group: 'trends', button: 'trendMap',
			takes: ['region', 'step', 'part', 'output', 'metric', 'alpha'].concat(SOURCE, PIXELS),
			defaults: {step: 'annual', output: 'slope', metric: 'mean'}},
		burn_severity: {group: 'fire', button: 'burn',
			takes: ['region', 'sensor', 'collection', 'start', 'end', 'other_start', 'other_end', 'index', 'metric',
				'quality', 'where', 'perimeter', 'burned_min', 'min_ha'],
			defaults: {sensor: 'Sentinel-2', index: 'dNBR', metric: 'median'}}
	};
	// the analyses of the services that the app computes as another one: the files of its maps and series
	var ALIASES = {map_figure: 'map_layer', download_image: 'map_layer', export_image: 'map_layer',
		download_rgb: 'rgb_map', download_comparison: 'compare_map', download_trend: 'trend_map',
		time_series_to_drive: 'time_series'};
	// the order of the parameters written, as that of the arguments of the services
	var PARAMETER_ORDER = ['region', 'line', 'variable', 'sensor', 'collection', 'ref', 'image', 'band', 'band_reducer',
		'band_scale', 'band_offset', 'unit', 'start', 'end', 'other_start', 'other_end', 'landcover', 'year', 'other_year',
		'breaks', 'trend', 'zones', 'index', 'step', 'part', 'output', 'metric', 'temporal', 'interannual', 'stat', 'alpha',
		'doy', 'other_variable', 'other_sensor', 'season', 'quality', 'where'];
	// areas.REGION_KEYS: the kinds of region of the services; the app takes some of them (applyRegion)
	var REGION_KEYS = ['geojson', 'file', 'wdpa_id', 'wdpa_name', 'ecoregion_id', 'ecoregion_at', 'biome_id', 'biome_at',
		'country', 'admin1', 'admin2', 'admin3', 'island_at', 'sea', 'sea_at', 'bbox', 'point'];

	var analysisSelect = null;  // the select of the analysis whose parameters are shown

	// NAME (a function of the services) is the analysis of the parameters: the one computed last
	function computed(name) {
		state.analysis = name;
		if (analysisSelect) analysisSelect.setValue(name, false);
	}

	function copyOf(x) {
		return JSON.parse(JSON.stringify(x));
	}

	function ordered(p) {
		var out = {};
		PARAMETER_ORDER.forEach(function (k) { if (p[k] !== undefined) out[k] = p[k]; });
		Object.keys(p).forEach(function (k) { if (!out.hasOwnProperty(k)) out[k] = p[k]; });
		return out;
	}

	// The variable of the catalog of the entry E as the services name it: its variable and sensor and, when they do not
	// find it (catalog.find takes the first entry that has them), its collection, and else its ref
	function variableParameters(e) {
		var p = {variable: e.index, sensor: e.sensor};
		if (mo.findEntry(e.index, e.sensor) !== e) p.collection = e.col;
		if (mo.findEntry(e.index, e.sensor, p.collection) !== e) p.ref = e.ref;
		return p;
	}

	// The data of Earth Engine of the entry E (dataEntry) as the services take them: their ID as a collection (images
	// with dates) or an image (a fixed layer), their band (or the bands combined, and band_reducer) and the scale,
	// offset and unit written
	function dataParameters(e) {
		var d = state.data, p = {};
		p[e.static ? 'image' : 'collection'] = e.col;
		p.band = e.reducer ? e.bands.slice() : e.band;
		if (e.reducer) p.band_reducer = e.reducer;
		var scale = numberOf(d.scale, t('bandScale')), offset = numberOf(d.offset, t('bandOffset'));
		if (scale !== null) p.band_scale = scale;
		if (offset !== null) p.band_offset = offset;
		if (String(d.unit || '').trim()) p.unit = String(d.unit).trim();
		return p;
	}

	// The pixel filters of the panel as the services take them (sensors.QUALITY): the Cloud Score+ only for Sentinel-2
	function qualityParameters(sensor) {
		var q = {};
		mo.FILTERS.forEach(function (f) { q[f] = Boolean(state.quality[f]); });
		if (sensor === 'Sentinel-2') q.cloud_score = state.quality.cloud_score;
		return q;
	}

	// The pixel filters of a profile of the entry E with the variable OE on the right axis as the services take them:
	// one quality for both variables (services._other_spec), resolved for each one (sensors.filters). Of each filter,
	// the value of the panel (with fixed filters on the left, SCF, CF or data by ID, which ignore it: that chosen for the
	// right axis) if it gives both axes those the app computes them with (the panel's, otherQuality), else 'auto' (on,
	// but for the variable that measures what it removes: the snow of the NDVI, not that of the NDSI, as the QGIS plugin
	// writes them); in NOTES, a filter that no value gives both axes as the app computes them (checked for a left
	// variable that measures what it removes, as the right one does: the app leaves it out of the right axis). The
	// Cloud Score+ when an axis is of Sentinel-2
	function profileQuality(e, oe, notes) {
		var fixed = mo.fixedFilters(e);
		var left = mo.filters(e, state.quality), right = mo.filters(oe, otherQuality(oe));
		var q = {};
		mo.FILTERS.forEach(function (f) {
			var panel = Boolean(fixed ? (state.chosenQuality ? state.chosenQuality[f] : true) : state.quality[f]);
			var fits = [panel, 'auto'].filter(function (v) {
				var one = {};
				one[f] = v;
				return mo.filters(e, one)[f] === left[f] && mo.filters(oe, one)[f] === right[f];
			});
			q[f] = fits.length ? fits[0] : panel;
			if (!fits.length) notes.push(fmt(t('paramsOtherFilter'), mo.entryName(oe), t(f)));
		});
		if (e.sensor === 'Sentinel-2' || oe.sensor === 'Sentinel-2') q.cloud_score = state.quality.cloud_score;
		return q;
	}

	// The conditions of «Only the pixels where» and of the land cover mask as the services take them (where), or null:
	// over PERIOD (whereArgs; default, that of the panel), written in those on a variable with dates only with OWN (an
	// analysis without dates of its own: a fixed layer)
	function whereParameters(period, own) {
		var conditions = whereArgs(period);
		if (!conditions) return null;
		return conditions.map(function (c) {
			if (mo.isLandcover(c)) return c;
			var out = variableParameters(mo.byRef(c.ref));
			['min', 'max', 'classes', 'exclude'].forEach(function (k) { if (c[k] !== undefined) out[k] = c[k]; });
			if (own && c.period) out.period = c.period;
			return out;
		});
	}

	// The options of Map (metric, temporal aggregation and metric between years) of the entry E: none for a fixed layer
	function mapParameters(p, e) {
		if (e.static) return;
		p.metric = state.mapMetric;
		p.temporal = state.temporal;
		if (state.temporal !== 'period') p.interannual = state.interannual;
	}

	// The parameters of the analysis ANALYSIS of the panel as the services take them (parameters.make): {parameters,
	// notes (what is missing to compute it)}; an Error with what the panel cannot compute (a date, a limit...)
	function parametersOf(analysis) {
		var p = {}, notes = [];
		if (ANALYSES[analysis].takes.indexOf('region') >= 0) {
			if (state.regionSpec) p.region = copyOf(state.regionSpec);
			else notes.push(t('paramsNoRegion'));
		}
		if (analysis === 'transect') {
			if (state.line) p.line = copyOf(state.line);
			else notes.push(t('paramsNoLine'));
		}
		if (analysis === 'burn_severity') {  // the sensor, or MODIS and its collection, Terra or Aqua (only the RdNBR)
			var modis = mo.RDNBR_MODIS.indexOf(state.fireSensor) >= 0;
			p.sensor = modis ? 'Modis' : state.fireSensor;
			if (modis) p.collection = state.fireSensor;
			p.start = state.fireBefore[0];
			p.end = state.fireBefore[1];
			p.other_start = state.fireAfter[0];
			p.other_end = state.fireAfter[1];
			p.index = state.fireIndex;
			p.quality = qualityParameters(p.sensor);
			var fireWhere = whereParameters(state.fireBefore, false);  // over the period before the fire, as the package
			if (fireWhere) p.where = fireWhere;
			return {parameters: ordered(p), notes: notes};
		}
		var kind = analysis === 'area_by_class' ? state.areaKind : null;
		if (kind === 'landcover') {
			var m = mo.landcoverMap(state.areaMap);
			p.landcover = m.key;
			p.year = state.areaYear || mo.landcoverDefaultYear(m);
			if (state.areaChangeOn) p.other_year = state.areaOther || mo.landcoverDefaultYear(m);
			return {parameters: ordered(p), notes: notes};
		}
		var e = entry();
		if (e.problem) throw new Error(e.problem);
		var source = e.custom ? dataParameters(e) : variableParameters(e);
		for (var k in source) p[k] = source[k];
		if (!e.static) {  // a fixed layer has no dates
			p.start = state.period[0];
			p.end = state.period[1];
			if (state.seasonOn) p.season = state.season.slice();
		}
		// the variable of the right axis of a profile: the pixel filters of both axes
		var oe = analysis === 'time_series' && isProfile() && state.doyOther !== 'none' ? mo.byRef(state.doyOther) : null;
		if (oe) p.quality = profileQuality(e, oe, notes);
		else if (!e.custom && !mo.fixedFilters(e)) p.quality = qualityParameters(e.sensor);
		var where = whereParameters(null, e.static);
		if (where) p.where = where;
		if (analysis === 'compare_map' || analysis === 'compare_series') {
			p.other_start = state.other[0];
			p.other_end = state.other[1];
		}
		if (['map_layer', 'rgb_map', 'compare_map', 'region_stats', 'transect'].indexOf(analysis) >= 0 ||
			kind === 'breaks') {
			mapParameters(p, e);
		}
		if (analysis === 'region_stats') {  // the zones of Gradients: a fixed layer cut at the breaks, or its classes
			var z = zoneEntry();
			p.zones = variableParameters(z);
			if (!mo.isCategorical(z)) p.zones.breaks = mo.checkBreaks(state.zoneBreaks);
		}
		if (kind === 'breaks') p.breaks = mo.checkBreaks(state.areaBreaks);
		if (kind === 'trend') p.trend = true;
		if (analysis === 'time_series' || analysis === 'compare_series') {
			p.step = state.step;
			p.metric = state.stepMetric;
			p.stat = state.stat;
		}
		if (analysis === 'time_series' && state.doy && state.step !== 'annual') {  // a line per year, or the profile
			p.doy = true;
			if (isProfile()) {
				p.interannual = state.doyBetween === 'years' ? 'median' : state.doyBetween;
				if (oe) {  // the services take the first entry of its variable and sensor (catalog.find), not another one
					p.other_variable = oe.index;
					p.other_sensor = oe.sensor;
					var first = mo.findEntry(oe.index, oe.sensor);
					if (first !== oe) notes.push(fmt(t('paramsOtherFirst'), mo.entryName(oe), oe.col, first.col));
				}
			}
		}
		if (analysis === 'trend_table' || analysis === 'trend_map' || kind === 'trend') {
			p.step = state.trendStep;
			if (analysis !== 'trend_table' && state.trendStep !== 'annual') {
				p.part = state.trendStep === '16-day' && state.trendPart > 23 ? 23 : state.trendPart;
			}
			p.metric = state.trendMetric;
		}
		if (analysis === 'trend_table') p.stat = state.stat;
		if (analysis === 'trend_map') {
			p.output = state.output;
			if (state.significant) p.alpha = 0.05;
		}
		if (analysis === 'timelapse') {
			p.step = state.animStep;
			p.metric = state.animMetric;
		}
		return {parameters: ordered(p), notes: notes};
	}

	// Show: the parameters of the analysis chosen in the box, as JSON (parameters.make), to copy them
	function showParameters() {
		var report = {shown: state.analysis, notes: [], skipped: []};
		try {
			var out = parametersOf(state.analysis);
			state.paramsText = JSON.stringify({monitoreo: mo.CATALOG.about.version, analysis: state.analysis,
				parameters: out.parameters});
			report.notes = out.notes;
		} catch (err) {
			report.error = err.message || String(err);
		}
		state.paramsReport = report;
		render();
	}

	// The value V of the option NAME as one of the ITEMS of its select (in any case, as the services take the texts):
	// SET with it and true; else listed as not applied, with the options of the app, and false
	function choose(name, v, items, set, skip) {
		function key(x) {
			return String(x).trim().toLowerCase();
		}
		var found = items.filter(function (i) { return key(i) === key(v); });
		if (!found.length) {
			skip(name, fmt(t('notOption'), items.join(', ')));
			return false;
		}
		set(found[0]);
		return true;
	}

	// areas._point: V as [lon, lat] (two numbers, in degrees), or an Error naming KEY
	function pointOf(v, key) {
		var p = Array.isArray(v) && v.length === 2 ? v.map(Number) : [];
		if (p.length !== 2 || !p.every(isFinite)) {
			throw new Error(key + ' is a point, [lon, lat] in degrees, e.g. [-3.3, 37.1]; not ' + JSON.stringify(v));
		}
		return p;
	}

	function bboxOf(v) {
		var b = Array.isArray(v) && v.length === 4 ? v.map(Number) : [];
		if (b.length !== 4 || !b.every(isFinite)) {
			throw new Error('bbox is [west, south, east, north] in degrees, e.g. [-3.62, 36.86, -3.5, 36.93]; not ' +
				JSON.stringify(v));
		}
		return b;
	}

	// The region R of the parameters (areas.region) as the region of the panel: a protected area (wdpa_id), an
	// administrative unit (admin1, admin2, admin3), seas (sea, by their MRGIDs or names), the ecoregion, island, sea or
	// biome (within a bbox: its part in the map view) at a point, a box (bbox) or polygons (geojson). Earth Engine is asked for the region (its names, its area), not
	// for the analysis. SKIP lists the regions the app cannot use (a file, a country...)
	function applyRegion(r, skip) {
		function refuse(reason) {
			skip('region', reason, r);
		}
		var isObject = r && typeof r === 'object' && !Array.isArray(r);
		var keys = isObject ? REGION_KEYS.filter(function (k) { return r[k] !== null && r[k] !== undefined; }) : [];
		if (keys.length !== 1) {  // areas.check
			return refuse((isObject ? 'give one region: ' : 'give the region as a dictionary with one of: ') +
				REGION_KEYS.join(', '));
		}
		var k = keys[0], v = r[k], within = r.within === null || r.within === undefined ? null : r.within;
		if (k === 'file') return refuse(t('regionFile'));
		var usable = ['wdpa_id', 'admin1', 'admin2', 'admin3', 'sea', 'sea_at', 'ecoregion_at', 'island_at', 'bbox',
			'geojson'].indexOf(k) >= 0 && within === null;
		var biome = k === 'biome_at' && within && typeof within === 'object' && within.bbox !== undefined &&
			Object.keys(within).length === 1;  // as a click on the map: its part in the map view
		if (!usable && !biome) return refuse(t('regionKind'));
		var spec = copyOf(r);
		try {
			if (k === 'wdpa_id') {
				var ids = (Array.isArray(v) ? v : [v]).map(Number);
				if (!ids.length || ids.some(function (x) { return !isFinite(x) || x !== Math.round(x); })) {
					throw new Error('wdpa_id is the WDPA ID (SITE_ID) of a protected area, or a list of them; not ' +
						JSON.stringify(v));
				}
				state.mode = 'wdpa';
				state.wdpaItems = null;
				message(t('loadingRegion'));
				mo.wdpaGeometries(ids).evaluate(function (info, error) {
					if (error) {
						refuse(String(error));
						render();
						return fail(error);
					}
					var fc;
					try {
						fc = mo.wdpaRegion(info);
					} catch (err) {
						refuse(err.message || String(err));
						render();
						return message(err.message || String(err), true);
					}
					results.style().set('shown', false);
					var names = info.features.map(function (f) { return f.properties.name; });
					state.wdpaId = ids[0];
					state.wdpaText = names[0] || state.wdpaText;
					setRegion(fc, names.join(', '), spec);
				});
			} else if (k === 'admin1' || k === 'admin2' || k === 'admin3') {
				var codes = Array.isArray(v) ? v : [v];
				if (codes.length !== 1) throw new Error(t('regionOne'));
				var level = Number(k.slice(-1));
				// level 3: a municipality of Spain, its code of the INE of 5 digits (an error that says so if not)
				var code = level === 3 ? mo.municipalityCodes(codes)[0] : Number(codes[0]);
				if (level !== 3 && !isFinite(code)) {
					throw new Error(k + ' is the GAUL code of an administrative unit; not ' + JSON.stringify(v));
				}
				state.mode = 'admin';
				state.adminLevel = level;
				state.adminCode = code;
				state.adminItems = null;
				setRegion(mo.adminRegion(level, code), null, spec, undefined, level);
			} else if (k === 'sea' || k === 'sea_at') {  // the seas of the IHO (Marine Regions): their credits shown
				var seas = k === 'sea' ? mo.seaRegion(v) : mo.seaAt.apply(null, pointOf(v, k));  // an error if not
				state.mode = 'sea';
				state.seaItems = null;
				state.seaId = k === 'sea' && !Array.isArray(v) && isFinite(Number(v)) ? Number(v) : null;
				setRegion(seas, null, spec, undefined, 'sea');
			} else if (k === 'ecoregion_at' || k === 'island_at') {
				var at = pointOf(v, k);
				state.mode = k === 'island_at' ? 'island' : 'ecoregion';
				setRegion(k === 'island_at' ? mo.islandAt(at[0], at[1]) : mo.ecoregionAt(at[0], at[1]), null, spec);
			} else if (k === 'biome_at') {
				var point = pointOf(v, k), inside = mo.bboxRegion(bboxOf(within.bbox)).geometry(mo.WITHIN_MAX_ERROR);
				state.mode = 'biome';
				setRegion(mo.withinRegion(mo.biomeAt(point[0], point[1], inside), inside), null, spec, ' · ' + t('mapView'));
			} else if (k === 'bbox') {
				state.mode = 'view';
				setRegion(mo.bboxRegion(bboxOf(v), t('mapView')), t('mapView'), spec);
			} else {  // areas._features_from_geojson: a geometry, a Feature or a FeatureCollection, each named
				var g = typeof v === 'string' ? JSON.parse(v) : v;
				var feats = g.type === 'FeatureCollection' ? g.features : g.type === 'Feature' ? [g] :
					[{type: 'Feature', geometry: g, properties: {}}];
				var names = feats.map(function (f, i) {
					var props = f.properties || {};
					var name = r.name_field ? props[r.name_field] : props.name !== undefined ? props.name : props.NAME;
					return String(name === undefined || name === null ? i + 1 : name);
				});
				state.mode = 'draw';
				setRegion(ee.FeatureCollection(feats.map(function (f, i) {
					return ee.Feature(ee.Geometry(f.geometry, null, false), {name: names[i]});
				})), names.join(', '), spec);
			}
			drawing.setShown(state.mode === 'draw');
		} catch (err) {
			refuse(err.message || String(err));
		}
	}

	// The data of Earth Engine by their ID of the parameters O (collection or image, band...): read (asynchronous),
	// then their band, scale, offset and unit set, or listed with SKIP. Returns what the panel computes then (a fixed
	// layer for an image)
	function applyData(o, skip) {
		var key = o.collection !== undefined ? 'collection' : 'image';
		if (o.collection !== undefined && o.image !== undefined) {
			skip('image', 'give collection (images with dates) or image (a fixed image), not both');
		}
		if (o.sensor !== undefined) skip('sensor', 'only for a variable of the catalog (variable and sensor)');
		var id = mo.assetId(o[key]);
		if (!id) {
			skip(key, 'give the ID of an image or a collection of images of Earth Engine');
			return entry();
		}
		if (!isData()) state.theme = 'earth_engine';
		readAsset(id, function (error, info) {
			if (error) return skip(key, error.message || String(error));
			var d = state.data;
			d.use = key === 'image' || !info.dated ? 'image' : 'collection';
			if (key === 'collection' && d.use === 'image') {  // variable.check_asset
				skip(key, info.type === 'image' ? id + ' is an image, not a collection of images: give it as an image (a ' +
					'fixed layer, without dates: maps, GeoTIFFs and statistics of the region)' : id + ' is a collection of ' +
					'images without dates (tiles): give it as an image (their mosaic, a fixed layer, without dates)');
			}
			var bands = mo.bandsOf(o.band);
			var missing = bands.filter(function (b) { return info.bands.indexOf(b) < 0; });
			var reducer = String(o.band_reducer === undefined ? '' : o.band_reducer).trim().toLowerCase();
			if (missing.length) {
				skip('band', id + ' has no band ' + missing.join(', ') + ': its bands are ' + info.bands.join(', '));
			} else if (bands.length > 1) {  // variable.check_bands
				if (mo.BAND_REDUCERS.indexOf(reducer) < 0) {
					skip('band', id + ": give band_reducer, 'sum' or 'mean', to combine its " + bands.length + ' bands (' +
						bands.join(', ') + ') into one value on each pixel');
				} else {
					d.combine = reducer;
					d.chosen = bands.slice();
					d.band = bands[0];
				}
			} else if (bands.length === 1) {
				d.band = bands[0];
				if (reducer) {
					skip('band_reducer', 'band_reducer combines several bands: give two or more in band (a list, or a text ' +
						'with commas)');
				}
			}
			[['band_scale', 'scale', 'bandScale'], ['band_offset', 'offset', 'bandOffset']].forEach(function (x) {
				if (o[x[0]] === undefined) return;
				try {
					var n = numberOf(o[x[0]], t(x[2]));
					d[x[1]] = n === null ? '' : String(n);
				} catch (err) {
					skip(x[0], err.message || String(err));
				}
			});
			if (o.unit !== undefined) {
				var unit = String(o.unit).trim();
				try {
					if (unit) mo.udunitsText(unit, id);  // its error now, as customEntry would give it
					d.unit = unit;
				} catch (err) {
					skip('unit', err.message || String(err));
				}
			}
		});
		return {custom: true, static: key === 'image'};
	}

	// What the parameters O compute: a variable of the catalog (catalog.find) chosen in its theme, or the data of
	// Earth Engine by their ID (applyData); without them, the variable of the panel. Returns its entry
	function applySource(o, skip) {
		var data = ['image', 'band', 'band_reducer', 'band_scale', 'band_offset', 'unit'];
		if (o.variable !== undefined || o.ref !== undefined) {
			var what = o.variable !== undefined ? o.variable : o.ref;
			data.forEach(function (k) {  // services.make_spec
				if (o[k] !== undefined) {
					skip(k, k + ': only for the data of Earth Engine given by their ID (collection or image, instead of ' +
						'variable and sensor); ' + what + ' is a variable of the catalog');
				}
			});
			var e;
			try {
				e = mo.findEntry(o.variable, o.sensor, o.collection, o.ref);
				if (e.two_periods) throw new Error(fmt(t('twoPeriods'), e.index));
			} catch (err) {  // parameters.check: the variable, the sensor and the collection with the reason
				['variable', 'sensor', 'collection', 'ref'].forEach(function (k) {
					if (o[k] !== undefined) skip(k, err.message || String(err));
				});
				return entry();
			}
			if (isData() || (state.theme !== 'all' && state.theme !== e.theme)) state.theme = e.theme;
			setVariable(e.ref);
			return e;
		}
		if (o.collection !== undefined || o.image !== undefined) return applyData(o, skip);
		['sensor'].concat(data).forEach(function (k) { if (o[k] !== undefined) skip(k, t('noSource')); });
		return entry();
	}

	// The burn severity of the parameters O (OPTIONS: with the defaults of the services): the index, the sensor (and,
	// for MODIS, its collection, Terra or Aqua) and the metric, the median. Returns the entry of the index (fireEntry)
	function applyFire(o, options, skip) {
		var fire = mo.themes().filter(function (th) { return (th.analyses || []).indexOf('burn_severity') >= 0; })[0];
		if (fire && state.theme !== 'all' && state.theme !== fire.key) setTheme(fire.key);
		var index = state.fireIndex;
		try {
			index = mo.burnIndex(options.index);
		} catch (err) {
			skip('index', err.message || String(err));
		}
		var sensor = mo.BURN_SENSORS[index].filter(function (s) {
			return mo.nameKey(s) === mo.nameKey(options.sensor);
		})[0];
		var fireSensor = state.fireSensor;
		var onlyModis = 'collection is only for the index RdNBR with sensor Modis (MODIS/061/MOD09GA, Terra, or ' +
			'MODIS/061/MYD09GA, Aqua)';
		if (!sensor) {
			try {
				mo.burnIndex(index, options.sensor);
			} catch (err) {
				skip('sensor', err.message || String(err));
			}
			if (o.collection !== undefined) skip('collection', onlyModis);
			if (mo.RDNBR_MODIS.indexOf(fireSensor) >= 0 && index !== 'RdNBR') fireSensor = 'Landsat';  // as fireWidgets
		} else if (sensor === 'Modis') {
			fireSensor = mo.RDNBR_MODIS[0];  // Terra, unless the collection is that of Aqua
			if (o.collection !== undefined) {
				choose('collection', o.collection, mo.RDNBR_MODIS, function (c) { fireSensor = c; }, skip);
			}
		} else {
			fireSensor = sensor;
			if (o.collection !== undefined) skip('collection', onlyModis);
		}
		state.fireIndex = index;
		state.fireSensor = fireSensor;
		choose('metric', options.metric, ['median'], function () {}, skip);
		['perimeter', 'burned_min', 'min_ha'].forEach(function (k) { if (o[k] !== undefined) skip(k, t('inResults')); });
		return fireEntry();
	}

	// The pixel filters QUALITY of the parameters (sensors.QUALITY: those not given, on; 'auto', on unless the variable
	// of the entry E measures what the filter removes) for E: not for those with fixed filters (SCF, CF, the fixed
	// layers, the data by ID), but for the variable of the right axis of a PROFILE (those chosen, otherQuality; 'auto',
	// on: the right axis leaves out that of what it measures)
	function applyQuality(e, quality, skip, profile) {
		var fixed = mo.fixedFilters(e);
		if (fixed && !profile) {
			if (quality !== undefined) skip('quality', e.custom ? t('customFilters') : t('fixedFilters'));
			return;
		}
		var q = {clouds: true, water: true, snow: true, aerosols: true, cloud_score: 0.6};
		if (quality !== undefined && (!quality || typeof quality !== 'object' || Array.isArray(quality))) {
			skip('quality', 'the pixel filters are a dictionary, e.g. {"clouds": true, "snow": false}');
		} else if (quality !== undefined) {
			Object.keys(quality).forEach(function (k) {
				var v = quality[k], one = {};
				one[k] = v;
				if (mo.FILTERS.indexOf(k) >= 0) {  // 'auto' with fixed filters: on (for the right axis)
					var auto = Boolean(fixed) || (mo.MEASURES[k] || []).indexOf(e.index) < 0;
					q[k] = String(v).toLowerCase() === 'auto' ? auto : Boolean(v);
				} else if (k === 'cloud_score' && (v === null || typeof v === 'number')) {
					q.cloud_score = v;
				} else {
					skip('quality', k === 'cloud_score' ? fmt(t('badNumber'), k, v) : t('noWidget'), one);
				}
			});
		}
		if (fixed) state.chosenQuality = q;
		else mo.FILTERS.forEach(function (f) { state.quality[f] = q[f]; });
		state.quality.cloud_score = q.cloud_score;
	}

	// The period, the other period (of a comparison; for a fire, the periods before and after it) and the season of
	// the parameters O
	function applyDates(analysis, o, skip) {
		var fire = analysis === 'burn_severity';
		var first = fire ? state.fireBefore : state.period, second = fire ? state.fireAfter : state.other;
		[['start', first, 0], ['end', first, 1], ['other_start', second, 0], ['other_end', second, 1]].forEach(function (x) {
			if (o[x[0]] === undefined) return;
			var text = String(o[x[0]]).trim();
			if (!DATE.test(text) || isNaN(mo.date(text).getTime())) return skip(x[0], fmt(t('badDate'), text));
			x[1][x[2]] = text;
		});
		if (fire) return;
		state.seasonOn = false;
		if (o.season === undefined) return;
		var season = (Array.isArray(o.season) ? o.season : String(o.season).split('/')).map(function (s) {
			return String(s).trim();
		});
		if (season.length !== 2 || !season.every(function (s) { return MONTH_DAY.test(s); })) {
			return skip('season', fmt(t('badDate'), JSON.stringify(o.season)));
		}
		state.seasonOn = true;
		state.season = season;
	}

	// The conditions WHERE of the parameters (variable.where_specs and the land cover mask): one on a variable (between
	// two values, or the classes of a categorical layer kept or left out) and one of land cover; computed over the
	// PERIOD of the analysis (of a fire, that before it; its own period only for a fixed layer E without dates: then
	// that of the panel)
	function applyWhere(where, e, o, skip, period) {
		state.whereOn = false;
		state.landcoverOn = false;
		if (where === undefined) return;
		var onVariable = false, onLandcover = false;
		(Array.isArray(where) ? where : [where]).forEach(function (c) {
			function refuse(reason) {
				skip('where', reason, c);
			}
			if (!c || typeof c !== 'object' || Array.isArray(c)) {
				return refuse('each condition of where is a dictionary with variable (and sensor), and min and/or max (or, ' +
					'for a categorical layer, classes or exclude), or with landcover, year and exclude (the land covers to ' +
					'leave out)');
			}
			if (mo.isLandcover(c)) {
				if (onLandcover) return refuse(t('whereOne'));
				try {
					var lc = mo.landcoverCheck(c);
				} catch (err) {
					return refuse(err.message || String(err));
				}
				state.landcoverOn = onLandcover = true;
				state.landcoverMap = lc[0].key;
				state.landcoverYear = lc[1];
				state.landcoverExclude = lc[2].slice();
				return;
			}
			if (onVariable) return refuse(t('whereOne'));
			var we;
			try {
				we = mo.findEntry(c.variable, c.sensor, c.collection, c.ref);
				if (we.two_periods) throw new Error(fmt(t('twoPeriods'), we.index));
			} catch (err) {
				return refuse(err.message || String(err));
			}
			if (mo.isCategorical(we)) {
				var keep = c.classes !== undefined && c.classes !== null ? 'classes' :
					c.exclude !== undefined && c.exclude !== null ? 'exclude' : null;
				if (!keep) return refuse(fmt(t('noCodes')));
				try {
					state.whereCodes = mo.checkClasses(we, c[keep], keep).join(', ');
				} catch (err) {
					return refuse(err.message || String(err));
				}
				state.whereKeep = keep;
			} else {
				if ((c.min === undefined || c.min === null) && (c.max === undefined || c.max === null)) {
					return refuse('the condition on ' + c.variable + ' of where needs min, max or both');
				}
				state.whereMin = c.min === undefined || c.min === null ? '' : String(c.min);
				state.whereMax = c.max === undefined || c.max === null ? '' : String(c.max);
			}
			state.whereOn = onVariable = true;
			state.whereRef = we.ref;
			// its own period: that of the panel, for a fixed layer without dates (as the app computes the condition)
			if (Array.isArray(c.period) && c.period.length === 2 && e && e.static && o.start === undefined &&
				o.end === undefined) {
				state.period = c.period.map(String);
			} else if (c.period !== undefined && c.period !== null && JSON.stringify(c.period) !==
				JSON.stringify(period)) {
				refuse(t('whereOwn'));
			}
			if (['metric', 'temporal', 'interannual', 'season', 'quality'].some(function (k) {
				return c[k] !== undefined && c[k] !== null;
			})) {
				refuse(t('whereOwn'));
			}
		});
	}

	// The options of the analysis ANALYSIS of the parameters O (OPTIONS: with the defaults of the services) of the
	// entry E, in the groups of the panel that compute it
	function applyOptions(analysis, e, o, options, skip) {
		function lower(v) {
			return typeof v === 'string' ? v.trim().toLowerCase() : v;
		}
		// the metric NAME of the images, or of each step or year: the only one of the variable, if it has one (SCF)
		function metric(name, set) {
			if (e && e.metric) {
				if (o[name] !== undefined && lower(o[name]) !== e.metric) {
					skip(name, e.index + ' (' + e.sensor + ") only takes the metric '" + e.metric + "'");
				}
				return set(e.metric);
			}
			choose(name, options[name], METRICS, set, skip);
		}
		function mapOptions() {
			metric('metric', function (m) { state.mapMetric = m; });
			choose('temporal', options.temporal, mo.TEMPORAL, function (v) { state.temporal = v; }, skip);
			choose('interannual', options.interannual, METRICS, function (v) { state.interannual = v; }, skip);
		}
		function part() {  // of the year of the trends: none for the year (or 0, its only part: trends.parts)
			if (state.trendStep === 'annual') {
				if (o.part !== undefined && Number(o.part) !== 0) {
					skip('part', 'part is a month (1-12) with step monthly, 1-23 with 16-day; none (or 0) with annual');
				}
				return;
			}
			if (o.part !== undefined) choose('part', o.part, mo.parts(state.trendStep), function (v) { state.trendPart = v; }, skip);
		}
		function significance() {  // the app takes the trends as significant with p < 0.05
			if (o.alpha !== undefined && Number(o.alpha) !== 0.05) skip('alpha', t('onlyAlpha'));
		}
		if (analysis === 'map_layer' || analysis === 'compare_map') state.mapLayer = 'index';
		if (analysis === 'rgb_map') state.mapLayer = 'rgb';
		if (['map_layer', 'rgb_map', 'compare_map', 'region_stats', 'transect'].indexOf(analysis) >= 0) mapOptions();
		if (analysis === 'timelapse') {
			choose('step', options.step, mo.ANIMATION_STEPS, function (v) { state.animStep = v; }, skip);
			metric('metric', function (m) { state.animMetric = m; });
		}
		if (analysis === 'time_series' || analysis === 'compare_series') {
			choose('step', options.step, analysis === 'time_series' ? mo.STEPS : mo.TREND_STEPS,
				function (v) { state.step = v; }, skip);
			metric('metric', function (m) { state.stepMetric = m; });
			choose('stat', options.stat, STATS, function (v) { state.stat = v; }, skip);
		}
		if (analysis === 'time_series') {  // a line per year over the days of the year, or the seasonal profile
			state.doy = Boolean(o.doy);
			state.doyBetween = 'years';
			state.doyOther = 'none';
			if (o.interannual !== undefined) {
				choose('interannual', o.interannual, BETWEEN, function (v) { state.doyBetween = v; }, skip);
			}
			if (o.other_variable !== undefined) {
				try {  // services.time_series: OTHER_SENSOR, by default SENSOR
					var oe = mo.findEntry(o.other_variable, o.other_sensor !== undefined ? o.other_sensor :
						e && !e.custom ? e.sensor : null);
					if (oe.static || oe.two_periods) throw new Error(t('withDates'));
					state.doyOther = oe.ref;
					if (state.doyBetween === 'years') state.doyBetween = 'median';
				} catch (err) {
					skip('other_variable', err.message || String(err));
					if (o.other_sensor !== undefined) skip('other_sensor', err.message || String(err));
				}
			} else if (o.other_sensor !== undefined) {
				skip('other_sensor', 'other_sensor is the sensor of other_variable');
			}
		}
		if (analysis === 'trend_table' || analysis === 'trend_map') {
			choose('step', options.step, mo.TREND_STEPS, function (v) { state.trendStep = v; }, skip);
			metric('metric', function (m) { state.trendMetric = m; });
		}
		if (analysis === 'trend_table') {
			choose('stat', options.stat, STATS, function (v) { state.stat = v; }, skip);
			significance();
		}
		if (analysis === 'trend_map') {
			part();
			choose('output', options.output, mo.OUTPUTS, function (v) { state.output = v; }, skip);
			if (o.alpha === undefined) state.significant = false;
			else if (Number(o.alpha) === 0.05) state.significant = true;
			else skip('alpha', t('onlyAlpha'));
		}
		if (analysis === 'region_stats') {  // the zones of Gradients
			var zones = o.zones;
			if (zones === undefined) {
				skip('zones', t('noZones'), null);
			} else {
				try {
					if (!zones || typeof zones !== 'object' || Array.isArray(zones)) throw new Error(t('zonesFixed'));
					var z = mo.findEntry(zones.variable, zones.sensor, zones.collection, zones.ref);
					if (!z.static) throw new Error(t('zonesFixed'));
					if (mo.isCategorical(z) && zones.breaks !== undefined && zones.breaks !== null) {
						throw new Error('the classes of ' + z.index + ' (' + z.sensor + ') are its own (a categorical layer, ' +
							'of class codes): give no breaks');
					}
					if (!mo.isCategorical(z)) state.zoneBreaks = mo.checkBreaks(zones.breaks).join(', ');
					state.zoneRef = z.ref;
					if (Object.keys(zones).some(function (k) {
						return ['variable', 'sensor', 'collection', 'ref', 'breaks'].indexOf(k) < 0 && zones[k] !== null;
					})) {
						skip('zones', t('zonesFixed'));
					}
				} catch (err) {
					skip('zones', err.message || String(err));
				}
			}
		}
		if (analysis === 'area_by_class') {  // a land cover map, the variable cut at some values, its trend or its classes
			var other = o.breaks !== undefined || o.trend ? 'give one of landcover, breaks or trend' : null;
			if (o.landcover !== undefined) {
				try {
					var m = mo.landcoverMap(o.landcover);
					var years = mo.landcoverYears(m);
					state.areaKind = 'landcover';
					state.areaMap = m.key;
					state.areaYear = mo.landcoverDefaultYear(m);
					if (o.year !== undefined) choose('year', o.year, years, function (y) { state.areaYear = y; }, skip);
					state.areaChangeOn = o.other_year !== undefined && choose('other_year', o.other_year, years,
						function (y) { state.areaOther = y; }, skip);
				} catch (err) {
					skip('landcover', err.message || String(err));
				}
				if (o.breaks !== undefined) skip('breaks', other);
				if (o.trend) skip('trend', other);
				return;
			}
			['year', 'other_year'].forEach(function (k) {
				if (o[k] !== undefined) skip(k, k + ': only with a land cover map (landcover)');
			});
			if (o.breaks !== undefined) {
				try {
					state.areaBreaks = mo.checkBreaks(o.breaks).join(', ');
					state.areaKind = 'breaks';
				} catch (err) {
					skip('breaks', err.message || String(err));
				}
				if (o.trend) skip('trend', other);
				options.metric = o.metric !== undefined ? o.metric : 'median';  // that of its map, as map_layer
				mapOptions();
			} else if (o.trend) {
				state.areaKind = 'trend';
				choose('step', options.step, mo.TREND_STEPS, function (v) { state.trendStep = v; }, skip);
				part();
				options.metric = o.metric !== undefined ? o.metric : 'mean';  // that of each year, as trend_map
				metric('metric', function (m) { state.trendMetric = m; });
				significance();
			} else {
				state.areaKind = 'classes';  // those of a categorical layer
			}
		}
	}

	// Apply: the panel set from the parameters TEXT (JSON of any tool, parameters.read): the analysis chosen and every
	// option it takes, the others of the services with their defaults, without computing; what cannot be applied is
	// listed under the box with the reason (parameters.check): not a parameter of that analysis in the app, an output,
	// a variable or a sensor that is not in the catalog, a region the app cannot use, a value its select does not have
	function applyParameters(text) {
		var report = {applied: null, notes: [], skipped: []};
		state.paramsReport = report;
		var p;
		try {
			p = mo.readParameters(text);
		} catch (err) {
			report.error = err.message || String(err);
			return render();
		}
		var given = p.analysis;
		var analysis = typeof given === 'string' && ALIASES.hasOwnProperty(given) ? ALIASES[given] : given;
		if (typeof analysis !== 'string' || !ANALYSES.hasOwnProperty(analysis)) {
			report.error = mo.PARAMETER_ANALYSES.indexOf(given) >= 0 ? fmt(t('noAnalysis'), given) :
				'unknown analysis ' + (given === null ? 'None' : typeof given === 'string' ? "'" + given + "'" : given) +
				': the parameters say which one in "analysis", one of ' + mo.PARAMETER_ANALYSES.join(', ');
			return render();
		}
		var a = ANALYSES[analysis], o = {}, options = {}, k;
		function skip(name, reason, value) {
			report.skipped.push({name: name, value: arguments.length > 2 ? value : p.parameters[name], reason: reason});
		}
		Object.keys(p.parameters).forEach(function (name) {
			var v = p.parameters[name];
			if (v === null || v === undefined) return;  // left empty: the value of the services (readme.call_args)
			if (mo.PARAMETER_OUTPUTS.indexOf(name) >= 0) return skip(name, t('anOutput'));
			if (a.takes.indexOf(name) < 0) return skip(name, fmt(t('notParameter'), analysis));
			o[name] = v;
		});
		report.applied = {given: given, analysis: analysis};
		if (p.monitoreo && p.monitoreo !== mo.CATALOG.about.version) {
			report.notes.push(fmt(t('paramsVersion'), p.monitoreo, mo.CATALOG.about.version));
		}
		for (k in a.defaults) options[k] = a.defaults[k];
		for (k in o) options[k] = o[k];
		computed(analysis);
		state.compareOn = analysis === 'compare_map' || analysis === 'compare_series';
		var landcover = analysis === 'area_by_class' && o.landcover !== undefined;  // a land cover map: no variable
		var e = analysis === 'burn_severity' ? applyFire(o, options, skip) : applySource(o, skip);
		if (!landcover) applyQuality(e, o.quality, skip, analysis === 'time_series' && o.other_variable !== undefined);
		applyDates(analysis, o, skip);
		applyOptions(analysis, e, o, options, skip);
		if (a.takes.indexOf('where') >= 0) {
			applyWhere(o.where, e, o, skip, analysis === 'burn_severity' ? state.fireBefore : state.period);
		}
		if (o.region !== undefined) applyRegion(o.region, skip);
		if (o.line !== undefined) skip('line', t('lineDrawn'));
		render();
	}

	// What Show or Apply said: the analysis set and its button, the notes, and what was not applied and why
	function reportWidgets() {
		var r = state.paramsReport;
		if (!r) return [];
		if (r.error) return [ui.Label(r.error, {fontSize: '12px', color: '#b00020', whiteSpace: 'pre-wrap'})];
		var warn = {fontSize: '12px', color: '#b06000', whiteSpace: 'pre-wrap'};
		var w = [];
		if (r.shown) w.push(ui.Label(fmt(t('paramsShown'), r.shown), SMALL));
		if (r.applied) {
			var a = ANALYSES[r.applied.analysis];
			w.push(ui.Label((r.applied.given !== r.applied.analysis ? fmt(t('paramsAlias'), r.applied.given,
				r.applied.analysis) + ' ' : '') + fmt(t('paramsSet'), r.applied.analysis, t(a.group), t(a.button)),
				{fontSize: '12px', color: '#1a73e8'}));
		}
		r.notes.forEach(function (n) { w.push(ui.Label(n, warn)); });
		if (r.skipped.length) {
			w.push(ui.Label(t('paramsNotApplied'), {fontSize: '12px', color: '#b06000', fontWeight: 'bold'}));
			r.skipped.forEach(function (s) { w.push(ui.Label('· ' + mo.parametersText([s]), warn)); });
		}
		return w;
	}

	// The parameters of the analysis as JSON, the same in every tool (monitoreo.parameters): the analysis (the last one
	// computed, or another), Show (its parameters in the box, to copy them: the Code Editor has no clipboard nor
	// files) and Apply (those pasted in the box), with what they said
	function parametersWidgets() {
		var w = [header(t('params'))];
		w.push(ui.Label(t('paramsHelp'), SMALL, mo.CATALOG.about.manual + (state.lang === 'en' ?
			'/Earth-Engine-app#parameters-of-the-analysis' : '/App-de-Earth-Engine#parámetros-del-análisis')));
		analysisSelect = select(Object.keys(ANALYSES).map(function (name) {
			return {value: name, label: name + ' · ' + t(ANALYSES[name].group)};
		}), state.analysis, function (v) { state.analysis = v; }, '270px');
		w.push(row(ui.Label(t('paramsAnalysis')), analysisSelect));
		var box = ui.Textbox({placeholder: t('paramsHint'), value: state.paramsText,
			onChange: function (v) { state.paramsText = v; }, style: {width: '340px'}});
		w.push(box);
		w.push(row(button(t('paramsShow'), showParameters), button(t('paramsApply'), function () {
			state.paramsText = box.getValue() || '';
			applyParameters(state.paramsText);
		})));
		return w.concat(reportWidgets());
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
		var fb = mo.CATALOG.about.feedback;
		controls.add(row(ui.Label('MonitorEO', {fontWeight: 'bold', fontSize: '22px', stretch: 'horizontal'}),
			button(t('language'), function () {
				state.lang = state.lang === 'es' ? 'en' : 'es';
				render();
			})));
		controls.add(ui.Label(t('subtitle'), SMALL));
		// the version of the package that the app was built from, and the date of its release (build.py)
		controls.add(ui.Label(fmt(t('version'), mo.CATALOG.about.version, mo.CATALOG.about.released),
			{fontSize: '11px', color: '#777'}));
		// suggestions and errors: an issue of GitHub or the anonymous form, filled with the app and its version
		controls.add(button(fb[state.lang].button, function () {
			state.feedbackOpen = !state.feedbackOpen;
			render();
		}));
		if (state.feedbackOpen) {
			controls.add(ui.Label('→ ' + fb[state.lang].issue, {fontSize: '12px', margin: '2px 8px'}, fb.links.issue));
			controls.add(ui.Label('→ ' + fb[state.lang].form, {fontSize: '12px', margin: '2px 8px'}, fb.links.form));
		}
		[regionWidgets(), landcoverWidgets(), variableWidgets(), mapWidgets(), areaWidgets(), gradientWidgets(),
			animationWidgets(),
			seriesWidgets(), trendWidgets(),
			themeHas('burn_severity') ? fireWidgets() : [], parametersWidgets(), aboutWidgets()].forEach(function (ws) {
			ws.forEach(function (w) { controls.add(w); });
		});
	}

	render();
})();
