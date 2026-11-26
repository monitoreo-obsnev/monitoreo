# MonitorEO Campo — diseño (APK local, uso personal)

## Objetivo
App Android para viajes de campo: elegir un punto (GPS actual, toque en el mapa, coordenadas escritas o una lista
preparada antes de salir) y calcular en Google Earth Engine las variables de MonitorEO en ese punto, como el plugin
de QGIS: valor del periodo, serie temporal y tendencia (Mann-Kendall + Sen). Los resultados quedan guardados en el
teléfono para verlos sin cobertura.

## Arquitectura
- **Android nativo mínimo (Java, sin dependencias AndroidX)**: una `Activity` con un `WebView` que sirve la interfaz
  desde `https://appassets.androidplatform.net/` (interceptando las peticiones con `shouldInterceptRequest`), para que
  la página sea un contexto seguro con origen https y la API de Earth Engine acepte las peticiones CORS.
- **Puente JS ↔ Java (`window.Android`)**, porque CORS y permisos son más simples en nativo:
  - `token()`: token de acceso de Earth Engine según el modo:
    - *cuenta de servicio*: JWT RS256 firmado en Java (`java.security`) con la clave del JSON, cambiado por un token en
      `https://oauth2.googleapis.com/token` (scope `earthengine`). El JSON se elige con el selector de archivos de
      Android y se guarda en `SharedPreferences` privadas de la app; la clave nunca pasa a la página web.
    - *cuenta compartida de MonitorEO (gratis)*: `GET {broker}/token?user=mo-<16 hex>`, como el paquete de Python
      (`services.BROKER`), con un ID anónimo generado en la instalación; `/usage` muestra las horas EECU que quedan.
  - `locate()`: posición actual con `LocationManager` (GPS + red), devuelta a JS con su precisión.
  - `pickServiceAccount()`, `saveFile(name, text)` para exportar resultados (CSV/GeoJSON) a Descargas.
- **Interfaz web (assets/)**: HTML + JS vanilla, Leaflet (mapa: OSM y Esri World Imagery), Chart.js (gráficos),
  cliente JS oficial de Earth Engine (`@google/earthengine` 1.7.48, la versión de `gee/package.json`).
- **Cálculo**: `catalog.js` y `core.js` de `monitoreo/gee` copiados tal cual al compilar → el mismo cálculo que la app
  de Earth Engine y el paquete de Python (`spec`, `seriesBins`, `series`, `seasonalBins`, `withParts`, `trendRows`,
  `image`, `autoScale`, `utmOf`). La app no reimplementa fórmulas ni filtros.
- **Región**: el punto con un radio elegible (0 = el píxel del punto; 30, 100, 250, 500 m), estadística media.

## Funciones
1. Puntos: lista guardada (localStorage); añadir por GPS / mapa / coordenadas; importar y exportar GeoJSON.
2. Análisis de un punto, con tema → variable del catálogo, periodo, radio:
   - Valor del periodo (composición media; sirve también para capas fijas: elevación, pendiente).
   - Serie temporal (mensual, 16 días o anual) con gráfico y CSV.
   - Tendencia anual: tabla Mann-Kendall (τ, p) + pendiente de Sen y gráfico.
   - Capa en el mapa (tiles de Earth Engine, solo con conexión).
3. Ficha rápida: un conjunto fijo de variables (NDVI S2 últimos 60 días, NDWI, LST, elevación, pendiente…) en una
   sola petición.
4. Precalcular: calcular la ficha (y, opcionalmente, la serie elegida) de todos los puntos antes de salir; todo
   resultado se guarda con fecha y se muestra sin red.
5. Ajustes: modo de cuenta, proyecto (por defecto el `project_id` del JSON), URL del broker, horas EECU restantes.

## Fuera de alcance
Mapas base sin conexión, análisis de fuego de dos periodos (RBR/RdNBR), exportar a Drive, publicación en Play Store.

## Riesgos
- Sin red no se calcula nada nuevo (Earth Engine es remoto): de ahí el precálculo y la caché.
- La cuenta de servicio debe estar registrada para Earth Engine en su proyecto.
- El broker comparte cuota (25 h EECU/mes por usuario): series largas a 10 m consumen; el radio y el paso lo limitan.
