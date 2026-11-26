# MonitorEO Campo: guía para integrarlo en `monitoreo`

Este documento explica a quien mantenga el repositorio
[monitoreo-obsnev/monitoreo](https://github.com/monitoreo-obsnev/monitoreo) (personas o agentes) qué es MonitorEO
Campo, cómo está hecho y qué usa de `monitoreo`, para llevarlo a ese repositorio como una herramienta más, igual que el
paquete de Python, el paquete de R, el plugin de QGIS, el servidor MCP, el asistente y la app de Earth Engine.

Estado a 2026-11-26: MonitorEO Campo 0.4.0 (repositorio privado `kampax/monitoreo-campo`), con el núcleo de MonitorEO
0.3.84 (`gee/core.js` y `gee/catalog.js` de `monitoreo` en `f4cf3a4..0b5a811`).

## 1. Qué es

Una app de Android para el trabajo de campo:

- **Puntos**: por GPS, tocando el mapa, por coordenadas o importados (GeoJSON, CSV). Se guardan en el teléfono.
- **Análisis de un punto**, con el mismo cálculo que la app de Earth Engine:
  - ficha rápida (NDVI, EVI, NDWI y NDSI de Sentinel-2 de 60 días, LST de Landsat de 90 días, precipitación ERA5-Land
    del último año, elevación y pendiente);
  - valor del periodo, serie temporal y tendencia anual (Mann-Kendall, Hamed-Rao o TFPW, más la pendiente de Sen,
    con temporada opcional);
  - capa de la variable en un círculo de 3 km.
  - Opciones de calidad de MonitorEO: corrección topográfica SCS+C y nieve por NDSI.
- **Sin cobertura**: los resultados quedan guardados con el punto (también la capa, como imagen). El mapa base de las
  zonas que se descarguen antes de salir se ve sin conexión, eligiendo el área y el detalle y con el tamaño estimado.
- **Asistente (pestaña Preguntar)**: un modelo de lenguaje decide qué calcular para responder una pregunta sobre los
  puntos, la app lo calcula con sus funciones y el modelo explica el resultado. Por defecto usa el modelo de MonitorEO
  a través del broker (`/chat`), como `monitoreo assistant`; opcionalmente, la clave propia del usuario de Claude,
  Gemini o GLM.
- **Cuentas de Earth Engine**: la cuenta compartida de MonitorEO, a través del broker (`/token`, `/usage`), o una cuenta
  de servicio del usuario (su JSON se guarda solo en el almacenamiento privado de la app).

## 2. Arquitectura

```
Android (Java, sin AndroidX)                       Página web local (assets/www)
┌──────────────────────────────┐  window.Android  ┌──────────────────────────────────────────┐
│ MainActivity                 │◄────────────────│ app.js   interfaz, puntos, mapa, cálculos  │
│  · WebView en                │  .call(cb, m, a)│ ai.js    asistente (Preguntar)            │
│    https://appassets.android │                 │ lib/core.js, lib/catalog.js  ← gee/ de    │
│    platform.net (contexto    │────────────────►│          monitoreo, SIN CAMBIOS           │
│    seguro; Earth Engine      │ AndroidCallback │ lib/ee_api_js.js  @google/earthengine     │
│    acepta su origen)         │   (cb, json)    │ lib/leaflet, lib/chart.umd.js             │
│  · claves (privadas)         │                 └──────────────────────────────────────────┘
│  · HTTP sin CORS             │                         │ Earth Engine (REST, con CORS)
│  · GPS, archivos             │                         ▼
│ Net: HTTP y JWT RS256 de la  │──► broker de MonitorEO: /token, /usage, /chat
│ cuenta de servicio           │──► APIs de Anthropic, Google (OpenAI-compatible) y Z.ai (clave del usuario)
└──────────────────────────────┘
```

- La página llama a Earth Engine directamente: el cliente JS de Earth Engine envía las peticiones REST con el token.
  El token sale del broker (cuenta compartida) o de la cuenta de servicio (lo firma `Net.java`).
- El broker no envía cabeceras CORS, así que la página no lo llama directamente: lo llama el código nativo (métodos
  `http` y `aiRequest`).
- **Ninguna clave llega a la página.** Ni el JSON de la cuenta de servicio ni las claves de IA: se guardan en
  `SharedPreferences` privadas (con `allowBackup=false`), y el código nativo las añade a una URL fija de cada
  proveedor.

### Métodos del puente (`window.Android.call(cbId, método, argumento)`)

| Método | Hilo | Qué hace |
|---|---|---|
| `pickServiceAccount` | UI | Elige el JSON de la cuenta de servicio (comprueba `type == service_account`) y lo guarda |
| `serviceAccountInfo` | pool | `{client_email, project_id}` de la cuenta guardada |
| `serviceAccountToken` | pool | Token de 1 h (JWT RS256, scopes earthengine y cloud-platform), en caché hasta 5 min antes de caducar |
| `clearServiceAccount` | pool | Olvida la cuenta |
| `http` | pool | `{method, url, body, contentType}` → `{status, body}`, sin CORS (el broker) |
| `aiKeys` / `aiSetKey` / `aiClearKey` | pool | Claves de IA por proveedor (`claude`, `gemini`, `glm`); solo devuelve los 4 últimos caracteres |
| `aiRequest` | pool | `{provider, body, url?, beta?}` → `{status, body}`; ver §5 |
| `openFile` / `saveFile` | UI | `ACTION_OPEN_DOCUMENT` / `ACTION_CREATE_DOCUMENT` (importar/exportar puntos, CSV) |
| `locate` | UI | GPS + red; termina con ≤ 8 m o a los 30 s; si no, la última posición conocida (`stale`) |
| `openUrl` | UI | Abre un enlace en el navegador (el manual) |
| `appInfo` | pool | `{version, code}` del APK |

### iPhone (`ios/`)

`ios/Campo/WebViewController.swift` y `Net.swift` repiten en Swift el puente de `MainActivity.java` y `Net.java`, con
los mismos métodos y respuestas. Las diferencias son estas:

- La página se sirve desde `campo://localhost` con un `WKURLSchemeHandler`, como hace Capacitor. En Android se sirve
  desde `https://appassets.androidplatform.net`.
- `window.Android` lo inyecta un `WKUserScript` que lo pasa a `webkit.messageHandlers.campo`. `app.js` y `ai.js` no
  cambian.
- Las claves de la cuenta de servicio y de la IA se guardan en el llavero. Si el llavero no las acepta, por una firma
  sin ese permiso, van a un archivo protegido de la app.
- La clave PKCS#8 se convierte a PKCS#1 para `SecKeyCreateWithData`.
- El GPS usa CoreLocation y pide la ubicación precisa si se concedió la aproximada.
- Los archivos se abren y guardan con `UIDocumentPickerViewController`.
- `alert`, `confirm` y `prompt` de la página se muestran como `UIAlertController`.

El proyecto se genera con XcodeGen (`ios/project.yml`). El workflow `.github/workflows/ios.yml` lo compila sin firma en
`macos-15` y empaqueta el `.ipa` con la versión de `app/build.gradle`. Sin probar en un iPhone real:

- falta confirmar que Earth Engine y Esri aceptan peticiones CORS desde el origen `campo://localhost`;
- falta confirmar que IndexedDB guarda las teselas y capas con ese esquema.

## 3. Qué usa de `monitoreo`

### `gee/core.js` y `gee/catalog.js`, sin cambios

`preparar.py` copia los dos archivos de `../monitoreo/gee` a `app/src/main/assets/www/lib/`. La app usa estas funciones
del objeto global `MonitorEO`:

- **Construcción del cálculo**: `variables`, `byRef`, `themes`, `spec`, `image`, `collection`, `checkDates`.
- **Series y tendencias**: `seriesBins`, `series`, `seasonalBins`, `withParts`, `windows`, `trendRows` (con el 7.º
  argumento `test`), `checkTest`, `TREND_TESTS`.
- **Escala y proyección**: `autoScale`, `utmOf`.
- **Capa**: `percentiles`, `visParams`, `rampEntry`.
- **Textos y opciones**: `unitOf`, `dataSource`, `wikiSection`, `noTopographic`, `SNOW_NDSI`, `SNOW_NDSI_DEFAULT`,
  `isDate`.

Cualquier cambio de firma de estas funciones en `core.js` rompe la app. Lo ideal es que la app entre en la paridad
(`gee/parity.js`) o en los tests de `core.js`.

### El broker (`broker/main.py`)

| Ruta | Uso en la app |
|---|---|
| `GET /token?user=mo-…` | Token de la cuenta compartida (`getToken` de `app.js`). Igual que las demás herramientas: workload tag = ID de la instalación (`ee.data.setDefaultWorkloadTag`). |
| `GET /usage?user=mo-…` | Horas EECU restantes y aviso de modo restringido (Ajustes, Precalcular). |
| `POST /chat?user=mo-…` | El modelo del asistente (§5). El cuerpo y la respuesta tienen el formato de OpenAI chat completions con `extra_content`, como `assistant.chat_cloud`. |

El ID anónimo (`mo-` + 16 hex) se genera en el teléfono con `crypto.getRandomValues` y se guarda en `localStorage`
(`campo.settings.userId`). Es el `services.user_id()` de la app.

No hacen falta cambios en el broker. Ideas opcionales:

- Un campo `client: "campo"` en `/chat` para separar en el log las peticiones de la app.
- Desplegar la 0.3.84 en Cloud Run: el broker desplegado el 2026-11-26 respondió con Claude Sonnet 5.5 a una petición de
  `glm-4.7-flash`, es decir, aún sin la clave de reserva de GLM.

## 4. Datos en el teléfono

- `localStorage`:
  - `campo.settings`: modo de cuenta, proyecto, `userId`, último formulario de Análisis, vista del mapa, opacidad de
    la capa, proveedor y modelos de IA.
  - `campo.points`: `[{id, name, lat, lon, created}]`.
- IndexedDB `campo`, versión 2:
  - `results` (clave `id`, índice `point`): cada resultado con `{id, point, kind, params, scale, crs, project, mode,
    source, computed, seconds, …}`.
    - `kind`: `ficha` (`items`), `value` (`stats`, `images`), `series` (`rows`), `trend` (`trend`, `years`, `first`)
      o `layer` (`bounds`, `vis`, `image`: un Blob PNG).
    - `id`: `punto|tipo|ref|periodo|radio|métrica|paso|temporada|calidad|test`. Recalcular lo mismo sustituye el
      resultado.
  - `tiles`: `{k: 'sat|topo/z/x/y', b: Blob}`, las teselas del mapa base sin conexión.
  - `areas`: las zonas descargadas `{id, name, bounds, zmin, zmax, bases, tiles, bytes, complete}`. Las teselas de una
    zona se deducen de sus límites y zooms; al borrar una zona se borran las que no use otra.

## 5. El asistente (`ai.js`)

Sigue el diseño de `monitoreo/assistant.py` y del broker para poder unificarlos.

- **Formato interno**: los mensajes de OpenAI chat completions. Lo que cada modelo necesita recibir de vuelta (el
  thinking de Claude, las firmas de pensamiento de Gemini) va en `extra_content` y se reenvía tal como llegó.
- **Proveedores** (Ajustes → Asistente):
  - `monitoreo` (por defecto): `POST {broker}/chat?user=ID` con `{messages, tools, temperature: 0.2}`. El broker elige
    el modelo (Claude Sonnet 5.5, o Gemini 3.8 Flash si Claude no tiene crédito) y guarda las claves.
  - `claude` (clave del usuario, modelo por defecto `claude-opus-5-5`): la página traduce como `claude_params` y
    `claude_answer` del broker. Eso incluye la caché, thinking adaptativo con `drop_block`
    (`thinking-binding-controls-2026-08-01`), effort `low` y `fallbacks: "default"`
    (`server-side-fallback-2026-07-01`) en Opus y Sonnet 5.5.
  - `gemini` (clave del usuario, `gemini-3.8-flash`): API compatible con OpenAI, con los esquemas y `extra_content`
    como `gemini_request` del broker.
  - `glm` (clave del usuario, `glm-4.7-flash`): como `chat_glm` de `assistant.py`. Usa solo los campos estándar y sin
    thinking. Si un modelo está ocupado prueba el siguiente gratuito (`glm-4.5-flash`). Si la clave falla (401/403) o
    no hay ninguna, pasa a la clave de reserva de GLM del broker.
- **Herramientas**: llaman a las mismas funciones que los botones de Análisis (`window.campo`).

  | Herramienta | Equivale a (MCP de monitoreo) |
  |---|---|
  | `puntos`, `ubicacion`, `guardar_punto` | (propias de la app) |
  | `variable` | `describe_variable` |
  | `resultados_guardados` | (propia: lo ya calculado en el teléfono) |
  | `ficha` | (propia) |
  | `valor` | `region_stats` de un punto/círculo |
  | `serie` | `time_series` |
  | `tendencia` | `trend_table` |
  | `capa` | `map_layer` (3 km, guardada como PNG) |

- **Cálculos largos**: antes de calcularlos, la app pide confirmación al usuario en el chat. Son las series de más de
  60 pasos, las tendencias de más de 12 años (o de más de 8 sin temporada con píxeles ≤ 30 m) y las capas de más de 2
  años con píxeles ≤ 30 m.
- **Límites**: 8 respuestas del modelo por mensaje (`MAX_STEPS`) y 2 MiB por petición al broker, como en
  `assistant.py`.

### Diferencia de criterio que hay que decidir al integrar

En `monitoreo assistant` el modelo **no ve los resultados**: recibe un recibo y la norma es no interpretarlos (reglas 1
y 2 de `PROMPT`). En MonitorEO Campo el modelo **recibe los valores agregados** de cada resultado (la media de un
punto, la serie, la tendencia con su p) y los explica. Las preguntas en el campo («¿está aumentando el NDVI aquí?») no
se pueden responder sin ellos.

Las instrucciones lo acotan:

- todo número debe salir de una herramienta;
- una tendencia solo es significativa con p < 0,05, y hay que dar n;
- las respuestas son breves y terminan con la fuente de los datos.

Al fusionar, el equipo debería decidir si es un modo propio de la app de campo o una opción del asistente. La página de
Ajustes ya avisa de que «la conversación y los valores calculados van a Anthropic o a Google».

## 6. Compilar y probar

- Requisitos:
  - JDK 17;
  - Android SDK (compileSdk/targetSdk 35, minSdk 26);
  - Gradle 9.4.1 (wrapper) y AGP 9.2.1;
  - sin dependencias de Maven más allá de AGP.
- Antes de compilar:
  - `python preparar.py` copia `catalog.js` y `core.js` de `../monitoreo/gee`;
  - `python preparar.py --npm DIR` copia además `ee_api_js.js` (@google/earthengine 1.7.48), Leaflet 1.9.4 y
    Chart.js 4.4.1.
- Compilar: `gradlew assembleRelease`. El APK queda firmado con la clave de depuración, solo para uso personal: para
  publicarlo hace falta una clave de firma propia (secreto de CI).
- Pruebas de escritorio (`tools/`):
  - `TestAuth.java`: el JWT de la cuenta de servicio;
  - `test_point.js`, `test_v02.js` y `test_layer.js`: los cálculos de `core.js` que hace la app, contra Earth Engine
    con Node.
- Las pruebas del asistente se hicieron en el navegador (`.claude/launch.json` → `campo-web`, puerto 8790):
  - `window.Android` simulado y un proxy local del broker para el CORS;
  - una conversación real con `/chat` y cálculos reales con la cuenta compartida;
  - los adaptadores de Claude, Gemini y GLM, con respuestas simuladas;
  - la clave de reserva de GLM, de verdad, a través del broker.

## 7. Propuesta de integración en `monitoreo`

1. **Carpeta `android/`** en la raíz (junto a `gee/`, `qgis/`, `r/`), con el proyecto Gradle tal cual. En el
   monorepo, `preparar.py` puede ser una tarea de Gradle (`preBuild`) que copie `gee/core.js` y `gee/catalog.js`, así
   la app siempre lleva el núcleo de su misma versión.
2. **Versión**: la de la app (`versionName`) puede seguir a la del paquete, como el plugin de QGIS. Así «Campo 0.3.84»
   significa núcleo 0.3.84.
3. **CI**: un trabajo en `.github/workflows/installers.yml` que use `setup-java@v4` (17) y el SDK de Android, ejecute
   `./gradlew assembleRelease` firmando con un keystore en los secretos y adjunte el APK a la release del tag.
4. **Ayuda y wiki**: una página «MonitorEO Campo» en español e inglés (instalar, cuentas, uso en el campo, asistente),
   como las demás herramientas. Los textos de la interfaz están hoy en español; para el inglés, los textos de `app.js`,
   `ai.js` e `index.html` tendrían que pasar a una tabla de traducciones.
5. **Asistente**: unificar el criterio de §5 y, si se quiere, compartir las instrucciones y las herramientas con
   `assistant.py`. Las herramientas de la app son un subconjunto, para puntos, de las del servidor MCP.
6. **Seguridad** (revisar en la PR):
   - claves solo en `SharedPreferences` privadas y `allowBackup=false`;
   - `usesCleartextTraffic=false`;
   - `aiRequest` solo acepta las URL fijas de cada proveedor o la ruta `/chat?user=mo-…` de un host https.

## 8. Archivos

| Archivo | Qué es |
|---|---|
| `app/src/main/java/es/ugr/monitoreo/campo/MainActivity.java` | WebView, puente, claves, GPS, archivos |
| `app/src/main/java/es/ugr/monitoreo/campo/Net.java` | HTTP (con cabeceras y tiempo de espera) y el JWT de la cuenta de servicio |
| `app/src/main/assets/www/index.html`, `style.css` | La interfaz (pestañas Mapa, Puntos, Análisis, Preguntar, Ajustes) |
| `app/src/main/assets/www/app.js` | Puntos, mapa (también sin conexión), cálculos (`analysis`, `computeValue/Series/Trend/Layer`, `computeFicha`), resultados, ajustes; expone `window.campo` |
| `app/src/main/assets/www/ai.js` | El asistente |
| `app/src/main/assets/www/lib/` | `core.js`, `catalog.js` (de `gee/`), `ee_api_js.js`, Leaflet, Chart.js |
| `preparar.py` | Copia lo de `lib/` |
| `tools/` | Pruebas de escritorio |
| `DISENO.md` | Diseño inicial y revisión |
| `README.md` | Instalar, usar, recompilar, versiones |
| `docs/maqueta-ia.*` | La maqueta del asistente |
