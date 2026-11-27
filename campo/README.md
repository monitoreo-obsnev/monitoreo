# MonitorEO Campo (APK local)

App Android para viajes de campo: puntos (GPS, toque en el mapa, coordenadas o GeoJSON/CSV importado) y las variables
de MonitorEO calculadas en Google Earth Engine en cada punto, con el mismo código que la app de Earth Engine
(`../monitoreo/gee/core.js` y `catalog.js`, copiados sin cambios). Diseño y revisión: `DISENO.md`.

## Instalar en el teléfono

1. Copia `MonitorEO-Campo-0.5.0.apk` al teléfono (cable, Drive, Telegram…) y ábrelo. Android pedirá permitir
   "instalar apps desconocidas" para la app desde la que lo abras.
   Con cable y depuración USB activada:

   ```bash
   "%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe" install -r MonitorEO-Campo-0.5.0.apk
   ```

2. Ajustes → cuenta:
   - **Cuenta compartida de MonitorEO** (por defecto): gratis, 25 h EECU al mes por instalación, sin configurar nada.
   - **Mi cuenta de servicio**: copia el JSON (p. ej. `earthcul-….json`) al teléfono, "Elegir JSON", y luego borra la
     copia de Descargas. La clave queda solo en el almacenamiento privado de la app (no se respalda). El proyecto es el
     `project_id` del JSON salvo que escribas otro.
3. "Probar conexión".

## Uso en el campo

- **Antes de salir** (con wifi): añade los puntos y pulsa *Puntos → Precalcular ficha de todos los puntos*; haz también
  las series o tendencias que quieras ver. Todo resultado queda guardado con su fecha y se ve sin cobertura.
- **En el campo**: ◎ en el mapa (o *+ Mi ubicación*) → guardar o *Analizar*. Con cobertura se calcula al momento.
- **Análisis**: ficha rápida (NDVI, EVI, NDWI, NDSI de Sentinel-2 de los últimos 60 días, LST de Landsat de 90 días,
  precipitación ERA5-Land del último año, elevación y pendiente), valor del periodo, serie temporal (mensual, 16 días o
  anual), tendencia anual (Mann-Kendall + Sen, con temporada opcional) y capa en el mapa (3 km alrededor del punto).
- Opciones de MonitorEO: corrección topográfica SCS+C de la reflectancia de Landsat (Sentinel-2 ya viene corregido),
  nieve también por su NDSI ≥ 0,4 (Sentinel-2 y Landsat) y test de la tendencia (Mann-Kendall, Hamed-Rao o TFPW, estos
  dos corrigen la autocorrelación de los valores anuales). Cada resultado dice qué datos usó, y ? abre la sección del
  manual de la variable.
- Radio: píxel del punto o círculo de 30–500 m. Si el píxel de la variable es mayor que el círculo (MODIS, clima), se
  usa el píxel del punto. Cada resultado dice el tamaño de píxel con el que se calculó.
- **Mapas sin conexión**: ⤓ en el mapa → encuadra la zona, elige el detalle máximo (de vista general a ~1 m/píxel) y
  satélite y/o topográfico; antes de descargar dice el tamaño de la zona, las teselas y los MB aproximados. Las zonas
  descargadas se ven o se borran en *Ajustes → Mapas sin conexión*. Uso personal: descarga solo lo que vayas a visitar.
- **Capa en el mapa**: se guarda como imagen (círculo de 3 km) con los resultados del punto; *Ver en el mapa* la pone
  encima del mapa también sin cobertura. En su leyenda se cambia la opacidad o se oculta y se vuelve a mostrar.
- **Preguntar**: escribe una pregunta sobre tus puntos («¿el NDVI de verano está aumentando aquí desde 2017?»). El
  asistente usa los resultados guardados o calcula lo que haga falta; antes de un cálculo largo pide confirmación.
  Cada resultado queda guardado con el punto. En *Ajustes → Asistente* eliges el modelo: el de MonitorEO (gratis, con
  un límite diario) o tu clave de Claude, Gemini o GLM. Necesita conexión.
- Sin cobertura no hay cálculos nuevos; sí los puntos, el GPS, los resultados guardados, las capas guardadas y el mapa
  base de las zonas descargadas.

## iPhone

La carpeta `ios/` es la misma app para iPhone. Usa la misma página (`app/src/main/assets/www`) y el mismo puente
`window.Android.call`, reescrito en Swift con WKWebView en `ios/Campo/*.swift`. Las claves se guardan en el llavero del
iPhone.

La compila GitHub en un Mac con el workflow `.github/workflows/ios.yml` cada vez que cambia `ios/` o la página. El
resultado es un artefacto `MonitorEO-Campo-<versión>-ios` con un `.ipa` sin firmar.

De momento se instala solo desde un ordenador, con [Sideloadly](https://sideloadly.io) o
[AltStore](https://altstore.io), y es para pruebas: no está en la App Store ni en TestFlight. Con Sideloadly, desde
Windows o Mac:

1. En Windows, instala iTunes de apple.com (no de la Microsoft Store). Después instala Sideloadly.
2. Conecta el iPhone por cable, arrastra el `.ipa` a Sideloadly, pon tu Apple ID y pulsa Start.
3. En el iPhone, ve a Ajustes › General › VPN y gestión de dispositivos y confía en tu Apple ID.
4. En Ajustes › Privacidad y seguridad, activa el Modo de desarrollador y reinicia el teléfono.

Con AltStore, instala AltServer en el ordenador y AltStore en el iPhone, y abre el `.ipa` desde AltStore; renueva la
firma solo, por Wi-Fi, mientras el ordenador esté encendido con AltServer.

Con un Apple ID gratuito la app caduca a los 7 días: se reinstala igual y los datos se conservan. Ese Apple ID tiene
como mucho 3 apps instaladas así a la vez, y conviene que sea uno secundario (Sideloadly y AltStore no son de Apple).
Con una cuenta de desarrollador de Apple dura un año.

## Recompilar

Tras `git pull` en `../monitoreo` basta con:

```bash
python preparar.py
```

Para actualizar también las librerías de npm:

```bash
python preparar.py --npm <carpeta con @google/earthengine 1.7.48, leaflet 1.9.4 y chart.js 4.4.1 extraídos de npm pack>
```

```bash
set JAVA_HOME=%USERPROFILE%\.gradle\jdks\eclipse_adoptium-17-amd64-windows.2
gradlew.bat assembleRelease
```

El APK queda en `app/build/outputs/apk/release/app-release.apk` (firmado con la clave de depuración: uso personal).
Ejecuta `preparar.py` tras actualizar el repositorio `monitoreo` para llevar a la app los cambios del catálogo y de
`core.js`.

## Pruebas en el escritorio

- `tools/TestAuth.java`: el flujo JWT de la cuenta de servicio de `Net.java` (devuelve un token).
- `tools/test_v02.js`: corrección topográfica, nieve por NDSI, los tres tests de tendencia y la capa (misma forma de
  ejecutarlo que el siguiente).
- `tools/test_layer.js`: la imagen de la capa que se guarda (PNG en Web Mercator sobre la caja del punto).
- `tools/test_point.js`: las llamadas de `core.js` que hace la app (ficha, valor, serie, tendencia, capa) en un punto de
  Sierra Nevada, contra Earth Engine: `node tools/test_point.js <carpeta con node_modules/@google/earthengine> token.json`.

## Versiones

- **0.5.0** (2026-11-26): la app está en español y en inglés.
  - El botón EN/ES de la cabecera cambia el idioma; se recarga la página y se conservan los puntos, los resultados y
    los ajustes.
  - Por defecto se usa el idioma del teléfono.
  - El asistente responde en el idioma elegido.
  - En Preguntar, el punto de la cabecera es un botón. Permite elegir:
    - la ubicación actual: usa el punto guardado que haya ahí o crea uno nuevo;
    - uno de los puntos guardados;
    - un punto nuevo tocando el mapa o escribiendo sus coordenadas.
  - Primera versión para iPhone (`ios/`).
- **0.4.0** (2026-11-26): asistente (pestaña Preguntar). Un modelo de lenguaje elige qué calcular, la app lo calcula
  con las mismas funciones que Análisis y el modelo explica el resultado. Por defecto usa el modelo de MonitorEO a
  través de su broker (sin clave); también acepta una clave propia de Claude, Gemini o GLM (Z.ai), guardada solo en
  la app. Núcleo de MonitorEO 0.3.84. Detalles e integración en `monitoreo`: `INTEGRACION.md`.
- **0.3.3** (2026-11-26): la leyenda de la capa tiene la opacidad (se recuerda) y un botón para ocultarla o mostrarla.
- **0.3.2** (2026-11-26): la versión instalada se ve en la cabecera y en Ajustes (con la del núcleo de MonitorEO).
- **0.3.1** (2026-11-26): la imagen de la capa se calcula al tamaño de píxel de la variable (10 m Sentinel-2, 30 m
  Landsat…; antes ~7 m para todas): con Landsat, 55 s → 8 s. Los cálculos muestran el tiempo que llevan.
- **0.3.0** (2026-11-26): mapas sin conexión (encuadrar una zona en el mapa, elegir el detalle y los mapas, ver el tamaño
  antes de descargar; lista en Ajustes para verlas o borrarlas) y la capa de la variable guardada como imagen con los
  resultados del punto, para verla sin cobertura.
- **0.2.0** (2026-11-24): núcleo de MonitorEO 0.3.81 (antes 0.3.49). Nuevas variables de Sentinel-2 (CLre, CLreB7,
  WAVI, albedo) y las de bandas de 20 m a 20 m; colores de la capa entre los percentiles 1 y 99; corrección
  topográfica de Landsat, nieve por NDSI y tests de tendencia con autocorrelación; fuente de los datos en cada
  resultado y enlace al manual; aviso cuando la cuenta compartida está en modo restringido.
- **0.1.0** (2026-11-15): primera versión.

## Citar

Observatorio de Cambio Global de Sierra Nevada (2026). MonitorEO [Software]. Zenodo.
https://doi.org/10.5281/zenodo.23814894 — Gorelick, N., et al. (2017). Google Earth Engine: Planetary-scale geospatial
analysis for everyone. Remote Sensing of Environment, 202, 18–27. https://doi.org/10.1016/j.rse.2017.06.031
