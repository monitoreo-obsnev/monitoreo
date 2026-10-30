"""Help of the options of the MonitorEO panel, shown by their buttons ⓘ: short texts in Spanish (rich text of Qt),
each ending with a link to the section of the manual (the wiki of the repository) that explains it. The help of the
variable and of the pixel filters also describes the variable chosen (variable_help, filters_help)."""

from . import deps

deps.setup_path()
from monitoreo import about, sensors, services  # noqa: E402

FILTER_NAMES = {'clouds': 'nubes', 'water': 'agua', 'snow': 'nieve', 'aerosols': 'aerosoles'}
MEASURED = {'water': 'el agua', 'snow': 'la nieve', 'aerosols': 'los aerosoles'}


def manual(page):
	return f'<p><a href="{about.MANUAL}/{page}">Más en el manual</a></p>'


HELP = {
	'project':
		'<p>Proyecto de Google Cloud registrado en Earth Engine: los cálculos se hacen con tu cuenta de Google y '
		'cuentan en la cuota de ese proyecto. Vacío: el de la variable de entorno EE_PROJECT (o '
		'GOOGLE_CLOUD_PROJECT). Se recuerda para la próxima vez.</p>'
		'<p><b>Autenticar…</b> abre el navegador para iniciar sesión con tu cuenta de Google, una vez en cada '
		'ordenador (como <code>earthengine authenticate</code>). <b>Conectar</b> comprueba que el proyecto funciona; '
		'no es obligatorio, porque cada cálculo se conecta solo.</p>' + manual('Primeros-pasos'),
	'region':
		'<p>Sobre qué se calcula:</p><ul>'
		'<li><b>Capa</b>: los polígonos de una capa del proyecto, los seleccionados o, si no hay selección, todos. '
		'Cada polígono da su propia serie.</li>'
		'<li><b>Extensión del mapa</b>: el rectángulo que se ve en el mapa al pulsar el botón del cálculo.</li>'
		'<li><b>Área protegida (WDPA)</b>: un área de la World Database on Protected Areas, buscada por su '
		'nombre.</li>'
		'<li><b>Ecorregión del centro del mapa</b>: la ecorregión de RESOLVE 2017 que contiene el centro de la '
		'vista.</li></ul>' + manual('Conceptos#regiones'),
	'layer':
		'<p>Capa de polígonos del proyecto, en cualquier sistema de coordenadas. Si tiene entidades seleccionadas, se '
		'usan solo esas; si no, todas. Cada polígono da su propia serie (una línea en la gráfica).</p>'
		'<p>Las capas con más de 20 000 vértices se simplifican antes de enviarlas a Earth Engine.</p>'
		+ manual('Conceptos#regiones'),
	'name_field':
		'<p>Campo con el nombre de cada polígono, que identifica sus series en la gráfica, la tabla y el CSV. Vacío: '
		'el número de la entidad en QGIS.</p>' + manual('Conceptos#regiones'),
	'wdpa':
		'<p>Escribe parte del nombre de un área protegida y pulsa <b>Buscar</b> (o Intro): la lista <b>Área</b> trae '
		'hasta 30 áreas de la <a href="https://www.protectedplanet.net">WDPA</a> con ese texto en su nombre.</p>'
		+ manual('QGIS#2-elegir-la-región'),
	'wdpa_area':
		'<p>El área protegida sobre la que se calcula. Cada entrada dice su nombre, su designación, su país, su '
		'superficie y su ID de WDPA.</p>'
		'<p>Fíjate en la designación: un mismo nombre suele tener varias figuras (parque nacional, parque natural, '
		'ZEC, ZEPA) con límites distintos.</p>' + manual('Conceptos#regiones'),
	'variable':
		'<p>Variable y sensor. Cada entrada dice la variable, el sensor, el tamaño del píxel y la colección de Earth '
		'Engine. Sentinel-2 (10 m) empieza en 2017; Landsat (30 m), en 1984, y MODIS (de 250 m a 4,6 km), en 2000: '
		'para series largas y tendencias, Landsat o MODIS.</p>',
	'period':
		'<p>Primer y último día, ambos incluidos. Cada sensor tiene sus fechas (ver la ayuda de <b>Variable</b>). Si '
		'marcas <b>Comparar con</b>, este es el periodo de referencia.</p>'
		'<p>Los periodos largos con Sentinel-2 sobre áreas grandes tardan minutos: empieza con un año.</p>'
		+ manual('Conceptos#periodo-y-temporada'),
	'compare':
		'<p>Marca <b>otro periodo</b> para compararlo con el de arriba, el de referencia:</p><ul>'
		'<li><b>Calcular la serie temporal</b> da la media de cada parte del año (mes, 16 días o año, según el '
		'<b>Paso</b>; el diario no vale) en cada periodo y su diferencia (otro − referencia).</li>'
		'<li><b>Añadir la capa al mapa</b> añade la diferencia de la métrica del mapa, con las bandas difference, '
		'reference y other.</li></ul>'
		'<p>Las tendencias y las exportaciones a Google Drive usan solo el periodo de referencia.</p>'
		+ manual('Conceptos#comparación-de-dos-periodos'),
	'season':
		'<p>Con la casilla <b>solo</b>, solo cuentan los días entre esas dos fechas (MM-DD) de cada año del periodo: '
		'de 06-01 a 09-30, el verano. Puede cruzar el año (de 11-01 a 02-28): entonces cuenta en el año en que '
		'empieza.</p><p>Vale para todo: series, mapas, tendencias, comparaciones y exportaciones.</p>'
		+ manual('Conceptos#periodo-y-temporada'),
	'filters':
		'<p>Quita de cada imagen, antes de calcular, los píxeles que sus bandas de calidad marcan con nubes (y sus '
		'sombras), agua, nieve o muchos aerosoles. Cada producto tiene sus bandas: los aerosoles solo se pueden '
		'quitar en Landsat 8 y 9 y en el NDVI, EVI y LAI de MODIS. En la app de MonitorEO estos filtros están '
		'desactivados por defecto.</p>'
		'<p>Desmarca el filtro de lo que mide la variable: <b>nieve</b> con el NDSI y <b>agua</b> con el NDWI, la '
		'Chl-a y el NDCI.</p>',
	'cloud_score':
		'<p>Solo para Sentinel-2, y con la casilla <b>nubes</b> marcada. Marcada, las nubes se quitan con Cloud Score+ '
		'de Google: un píxel es claro si su puntuación es al menos 0,6. Sin marcar, con la clasificación de escena '
		'(SCL) de Sentinel-2 (sombras, nubes y cirros), como la app de MonitorEO.</p>'
		+ manual('Conceptos#filtros-por-píxel'),
	'step':
		'<p>Cada cuánto da un valor la serie: <b>Mensual</b>, <b>Anual</b>, <b>16 días</b> (bloques de 16 días desde '
		'el 1 de enero de cada año) o <b>Diario</b> (cada día con imágenes). Los pasos largos tardan menos y tienen '
		'menos huecos por las nubes.</p><p>Para comparar periodos, mensual, 16 días o anual.</p>'
		+ manual('Conceptos#del-montón-de-imágenes-a-un-número-métrica-y-estadístico'),
	'ts_metric':
		'<p>Cómo se resumen en cada píxel las imágenes de cada paso: con paso mensual y <b>Media</b>, la media de las '
		'imágenes de cada mes. La mediana y los percentiles resisten mejor los valores anómalos, como nubes que se '
		'escapan a los filtros.</p>'
		+ manual('Conceptos#del-montón-de-imágenes-a-un-número-métrica-y-estadístico'),
	'stat':
		'<p>Cómo se resumen los píxeles de la región (de cada polígono) en un valor por paso, después de la métrica de '
		'cada paso. La <b>Desviación típica</b> mide lo distintos que son los píxeles entre sí.</p>'
		'<p>También es el estadístico de la <b>Tabla de tendencias de la región</b> y de la comparación de '
		'periodos.</p>' + manual('Conceptos#del-montón-de-imágenes-a-un-número-métrica-y-estadístico'),
	'series_list':
		'<p>Series temporales, tablas de tendencias y comparaciones calculadas en esta sesión de QGIS. Elige una y '
		'pulsa <b>Ver</b> para abrir otra vez su ventana, con la gráfica, la tabla y los botones <b>Guardar CSV…</b> y '
		'<b>Guardar gráfica…</b>.</p><p>La lista se pierde al cerrar QGIS: guarda lo que quieras conservar.</p>'
		+ manual('QGIS#5-calcular-la-serie-temporal'),
	'trend_step':
		'<p>Partes del año cuya tendencia se calcula a lo largo de los años del periodo: <b>Año</b> (el año entero, o '
		'la temporada si está marcada), <b>Meses</b> (cada uno de los 12) o <b>16 días</b> (23 bloques desde el 1 de '
		'enero). Cada año da un valor de cada parte; con esos valores, el test de Mann-Kendall dice si hay tendencia y '
		'la pendiente de Sen, cuánto cambia la variable por año.</p>'
		'<p>Hacen falta al menos 2 años, y mejor 8 o más: para series largas, Landsat o MODIS.</p>'
		+ manual('Conceptos#tendencias-estacionales-mann-kendall-y-sen'),
	'trend_metric':
		'<p>Cómo se resumen las imágenes de cada parte del año en cada año: con <b>Meses</b> y <b>Media</b>, la media '
		'de las imágenes de cada julio. En la tabla, ese valor se calcula para la región con el <b>Estadístico de la '
		'región</b> del grupo Serie temporal; en el mapa, en cada píxel.</p>'
		+ manual('Conceptos#tendencias-estacionales-mann-kendall-y-sen'),
	'trend_part':
		'<p>La parte del año que pinta el <b>Mapa de tendencia</b>: un mes o un bloque de 16 días (con <b>Año</b>, el '
		'año entero).</p>'
		'<p>El mapa tiene seis bandas por píxel: pendiente de Sen (la que se pinta, de rojo, descenso, a verde, '
		'aumento), τ de Kendall, Z, p-valor, ordenada (el valor de la recta en el primer año) y número de años con '
		'datos. Consúltalas con <b>Identificar</b>.</p>'
		+ manual('QGIS#6-tendencias'),
	'trend_alpha':
		'<p>Marcada, el mapa de tendencia solo muestra los píxeles con tendencia significativa (p-valor &lt; 0,05); '
		'los demás quedan sin datos. Sin marcar, muestra todos.</p>'
		'<p>Un p-valor alto no prueba que no haya cambio: con pocos años o mucha variabilidad, el test no tiene '
		'potencia para verlo.</p>' + manual('Conceptos#tendencias-estacionales-mann-kendall-y-sen'),
	'map_metric':
		'<p>Cómo se resumen en cada píxel las imágenes del periodo (o de cada año o mes, según la <b>Agregación '
		'temporal</b>). La <b>Mediana</b> resiste mejor que la media los valores anómalos.</p>'
		'<p>Con <b>Comparar con</b> marcado, se calcula en los dos periodos y la capa es su diferencia.</p>'
		+ manual('Conceptos#mapas-agregación-en-el-tiempo'),
	'temporal':
		'<ul><li><b>Todo el periodo</b>: la métrica de todas las imágenes del periodo.</li>'
		'<li><b>Cada año y entre años</b>: la métrica de cada año y, después, la <b>Métrica entre años</b> de esos '
		'valores. Con Máximo y Mediana, la mediana de los máximos anuales.</li>'
		'<li><b>Cada mes y entre años</b>: la métrica de cada mes; después, la métrica entre años de cada mes del '
		'calendario (p. ej. la media de todos los julios) y, al final, la media de esos meses.</li></ul>'
		+ manual('Conceptos#mapas-agregación-en-el-tiempo'),
	'interannual':
		'<p>Solo con <b>Cada año y entre años</b> o <b>Cada mes y entre años</b>: cómo se combinan los valores de los '
		'distintos años. Con <b>Todo el periodo</b> no se usa.</p>'
		+ manual('Conceptos#mapas-agregación-en-el-tiempo'),
	'resolution':
		'<p>Tamaño del píxel del GeoTIFF de <b>Mapa (GeoTIFF)</b>, en metros. Con 0, <i>la de los datos</i>: 10 m en '
		'Sentinel-2, 30 m en Landsat y de 250 m a 4,6 km en MODIS. Un píxel mayor da un fichero más pequeño y una '
		'exportación más rápida.</p>'
		'<p>Las capas de <b>Añadir la capa al mapa</b> no la usan: van a la resolución de los datos hasta 4 millones '
		'de píxeles y, en regiones mayores, con píxeles más grandes.</p>' + manual('QGIS#8-exportar-a-google-drive'),
	'folder':
		'<p>Carpeta de tu Google Drive donde Earth Engine deja los ficheros; si no existe, la crea. Las exportaciones '
		'no tienen límite de tamaño y siguen en Earth Engine aunque cierres QGIS. El panel sigue cada tarea y avisa al '
		'terminar; con Google Drive para escritorio, el GeoTIFF se añade al proyecto en cuanto se sincroniza.</p>'
		'<p>El mapa usa las opciones del grupo <b>Mapa</b>, y la serie, las del grupo <b>Serie temporal</b>.</p>'
		+ manual('QGIS#8-exportar-a-google-drive'),
}


def describe(v):
	"""Description of the catalog of V, an item of services.list_variables."""
	return services.describe_variable(v['variable'], v['sensor'], v['collection'])


def filter_lines(v, d):
	"""The filters that can be applied to V (described by D) and those that remove what it measures."""
	names = [FILTER_NAMES[f] for f in sensors.FILTERS if d['pixel_filters'].get(f)]
	out = [f"Con {v['variable']} de {v['sensor']} se pueden quitar: {', '.join(names) or 'ningún filtro'}."]
	for f in d['measures']:
		if d['pixel_filters'].get(f):
			out.append(f"<b>{v['variable']} mide {MEASURED[f]}: desmarca {FILTER_NAMES[f]}</b>, o lo quitará.")
	return out


def variable_help(v):
	"""Help of the variable: the general text and the variable V chosen."""
	d = describe(v)
	unit = v['unit'].strip('[]')
	lines = [f"<b>{v['variable']} · {v['sensor']}</b>: {d['name']} ({d['group']}).",
	         f"Unidad: {'sin unidades' if unit == 'unitless' else unit}. Píxel de {v['resolution_m']} m. Fechas: "
	         f"{v['dates'].replace('now', 'hoy')}. Colección: {v['collection']}."] + filter_lines(v, d)
	return HELP['variable'] + ''.join(f'<p>{line}</p>' for line in lines) + manual('Conceptos#variables')


def filters_help(v):
	"""Help of the pixel filters, with those of the variable V chosen."""
	lines = filter_lines(v, describe(v))
	return HELP['filters'] + ''.join(f'<p>{line}</p>' for line in lines) + manual('Conceptos#filtros-por-píxel')
