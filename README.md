# MonitorEO en Python, QGIS, R y modelos de lenguaje

Las variables de satélite de [MonitorEO](https://ee-ugr-default-project.projects.earthengine.app/view/monitoreo-obsnev)
(OBSNEV, Universidad de Granada), calculadas con Google Earth Engine desde cuatro herramientas que usan **las mismas
funciones** (`monitoreo.services`):

| Herramienta | Para quién | Dónde |
|---|---|---|
| Paquete de Python `monitoreo` | scripts, cuadernos, línea de comandos | `src/monitoreo` |
| Plugin de QGIS **MonitorEO** | usuarios de QGIS 3 y 4 | `qgis/monitoreo_qgis` |
| Servidor MCP | Claude u otros modelos de lenguaje | `src/monitoreo/mcp_server.py` |
| Paquete de R `monitoreo` | R, con `rgee` | `r/monitoreo` |

Qué calculan, sobre una región (un área protegida de WDPA, una ecorregión, un rectángulo, un punto, una capa o un
GeoJSON):

- **Series temporales**: un valor por día, 16 días, mes o año y por cada polígono de la región, con el número de
  imágenes y de píxeles válidos de cada valor; en tabla, CSV y gráfica.
- **Mapas** de la variable agregada en el tiempo (p. ej. la mediana del NDVI de un periodo) como capa de teselas de
  Earth Engine: se ven en QGIS, Leaflet o rgee sin descargar nada.
- **Estadísticas** de esos mapas en cada polígono.
- **Exportaciones** a Google Drive de mapas (GeoTIFF) y series (CSV) grandes.

Variables: las 32 del catálogo de MonitorEO (NDVI, EVI, NDWI, LSWI, NDSI, NDCI, albedo, temperatura de superficie,
evapotranspiración, calor latente, LAI, clorofila, aerosoles) de Sentinel-2, Landsat 5-9 y MODIS, y cualquier otra
colección o imagen de Earth Engine. Por defecto se aplican los **filtros por píxel** de MonitorEO (nubes, agua,
nieve, aerosoles), que en la app están desactivados; las nubes de Sentinel-2 se quitan con Cloud Score+.

Todo se calcula con **la cuenta de Earth Engine de cada usuario** y su proyecto de Google Cloud: no hay servidor
que alojar ni coste (el uso no comercial de Earth Engine es gratuito, con una cuota mensual por proyecto).

## Antes de empezar: cuenta de Earth Engine

1. Un proyecto de Google Cloud registrado en Earth Engine para uso no comercial
   (https://developers.google.com/earth-engine/guides/access).
2. Iniciar sesión una vez en el ordenador:

   ```bash
   earthengine authenticate
   ```

   (en QGIS, el botón **Autenticar…** del panel hace lo mismo). Las credenciales se guardan en
   `~/.config/earthengine/credentials` y las usan todas las herramientas.
3. El proyecto se indica en cada herramienta o en la variable de entorno `EE_PROJECT`.

## Instalación (Python, MCP y R)

Con [Miniforge](https://github.com/conda-forge/miniforge) (solo conda-forge; Miniconda usa por defecto el canal
`defaults` de Anaconda, cuyas condiciones exigen licencia a organizaciones grandes), desde la carpeta del repositorio:

```bash
conda env create -f environment.yml
conda activate monitoreo
```

o con pip en cualquier entorno de Python 3.9 o posterior:

```bash
pip install "monitoreo[mcp,plot] @ git+https://github.com/monitoreo-obsnev/monitoreo"
```

GDAL solo hace falta para leer ficheros vectoriales como región y descargar GeoTIFF directamente; el entorno de conda
lo trae.

## Python

```python
from monitoreo import services as mo

mo.init('mi-proyecto')                       # o la variable EE_PROJECT
mo.find_protected_areas('Sierra Nevada')     # SITE_ID = ID de WDPA (Parque Nacional: 389011)

ts = mo.time_series({'wdpa_id': 389011}, 'NDVI', 'Sentinel-2', '2020-01-01', '2021-12-31',
                    step='monthly', metric='mean', stat='mean', csv='ndvi.csv', chart='ndvi.png')
ts['rows'][:2]   # [{'region': 'Sierra Nevada', 'date': '2020-01-01', 'value': 0.34, 'n_pixels': ..., 'n_images': 31}, ...]

capa = mo.map_layer({'wdpa_id': 389011}, 'LST', 'Modis', '2021-06-01', '2021-08-31', metric='mean',
                    thumbnail='lst.png')
capa['url']      # https://earthengine.googleapis.com/v1/projects/.../tiles/{z}/{x}/{y}

mo.region_stats({'ecoregion_id': 793}, 'NDVI', 'Modis', '2021-01-01', '2021-12-31')
tarea = mo.export_image({'wdpa_id': 389011}, 'NDVI', 'Sentinel-2', '2021-01-01', '2021-12-31',
                        resolution=10, folder='MonitorEO')
mo.task_status(tarea['operation'])
```

Regiones: `{'wdpa_id': 389011}` (o una lista), `{'wdpa_name': 'Sierra Nevada'}`, `{'ecoregion_id': 793}`,
`{'ecoregion_at': [lon, lat]}`, `{'bbox': [oeste, sur, este, norte]}`, `{'point': [lon, lat], 'buffer': 1000}`,
`{'geojson': ...}` (geometría, Feature o FeatureCollection; `name_field` da el nombre de cada polígono) o
`{'file': 'zonas.gpkg', 'name_field': 'nombre'}`. Con varios polígonos hay una serie por polígono.

Opciones comunes: `season=['06-01', '09-30']` (solo esos días de cada año), `quality={'snow': False}` (filtros por
píxel: `clouds`, `water`, `snow`, `aerosols`, `True`, `False` o `'auto'`; `cloud_score: None` usa la máscara SCL de
MonitorEO en lugar de Cloud Score+), `metric` (`mean`, `median`, `min`, `max`, `pN`...) y, en los mapas,
`temporal='annual'` + `interannual='median'` (la métrica de cada año y después entre años).

Línea de comandos:

```bash
monitoreo list --sensor Landsat
monitoreo info NDVI --sensor Modis
monitoreo parks "Doñana"
monitoreo series NDVI --sensor Sentinel-2 --region '{"wdpa_id": 389011}' --start 2020-01-01 --end 2021-12-31 --csv ndvi.csv --png ndvi.png
```

## Plugin de QGIS

Instalación: **Complementos > Administrar e instalar complementos > Instalar a partir de ZIP** con
`dist/monitoreo_qgis-0.1.0.zip`. El zip lleva dentro `monitoreo` y la librería de Earth Engine con sus dependencias
(Python puro, válido en Windows, macOS y Linux), así que no hay que instalar nada más. Está probado en QGIS 3.40
LTR (Qt5, Python 3.9) y QGIS 4.0 (Qt6, Python 3.12); declara QGIS 3.22 como versión mínima.

El botón **MonitorEO** de la barra de herramientas (o el menú Web) abre un panel con:

- **Google Earth Engine**: el proyecto, **Conectar** y **Autenticar…**.
- **Región**: una capa de polígonos (las entidades seleccionadas o todas, con un campo para su nombre), la
  extensión del mapa, un área protegida (buscando por nombre en WDPA) o la ecorregión del centro del mapa.
- **Variable**: variable y sensor del catálogo, periodo, temporada y filtros por píxel.
- **Serie temporal**: paso, métrica de cada paso y estadístico de la región. Abre una ventana con la gráfica, la tabla
  y los botones para guardar el CSV y la gráfica.
- **Mapa**: añade la capa de teselas de Earth Engine al proyecto (se calcula al verla; la URL vale unas horas).
- **Exportar a Google Drive**: el mapa en GeoTIFF y la serie en CSV. El panel sigue las tareas y, si Google Drive
  para escritorio está instalado, carga el GeoTIFF en el proyecto al terminar.

Los cálculos van en tareas de QGIS (barra de tareas), sin bloquear QGIS.

Para generar el zip: `python qgis/build_plugin.py` (descarga las dependencias; necesita internet). Prueba sin
ventana con el Python de QGIS: `EE_PROJECT=... /Applications/QGIS-LTR.app/Contents/MacOS/bin/python3.9 qgis/test_plugin.py`.

## Servidor MCP (Claude y otros modelos de lenguaje)

Herramientas: `list_variables`, `describe_variable`, `find_protected_areas`, `time_series` (tabla, CSV y gráfica),
`map_layer` (URL de teselas y vista previa), `region_stats`, `export_image_to_drive`,
`export_time_series_to_drive`, `task_status` y `connect`. Los CSV y PNG se guardan en `MONITOREO_OUTPUT` (por defecto
`~/MonitorEO`).

Claude Desktop (`claude_desktop_config.json`), con el entorno de conda:

```json
{
  "mcpServers": {
    "monitoreo": {
      "command": "/ruta/a/miniforge3/envs/monitoreo/bin/monitoreo",
      "args": ["mcp"],
      "env": {"EE_PROJECT": "mi-proyecto", "MONITOREO_OUTPUT": "/Users/yo/MonitorEO"}
    }
  }
}
```

o siempre con la última versión de GitHub, con [uv](https://docs.astral.sh/uv/):

```json
"command": "uvx",
"args": ["--from", "monitoreo[mcp,plot] @ git+https://github.com/monitoreo-obsnev/monitoreo", "monitoreo", "mcp"]
```

Claude Code:

```bash
claude mcp add monitoreo -e EE_PROJECT=mi-proyecto -- /ruta/a/miniforge3/envs/monitoreo/bin/monitoreo mcp
```

Ejemplo de petición: *"Compara el NDVI mensual de Sentinel-2 de 2019 a 2023 en el Parque Nacional de Sierra Nevada
y en el de Doñana y dame el CSV"*. Las series largas sobre áreas grandes tardan minutos: mejor con paso mensual o
anual, o exportadas a Drive.

## R

```r
# install.packages(c("reticulate", "rgee"))      # rgee es opcional
install.packages("r/monitoreo", repos = NULL, type = "source")
library(monitoreo)

# El Python de reticulate debe tener el paquete monitoreo: el del entorno de conda,
Sys.setenv(RETICULATE_PYTHON = "/ruta/a/miniforge3/envs/monitoreo/bin/python")
# o el de rgee, instalándolo en él con mo_install().
mo_init("mi-proyecto")

mo_protected_areas("Sierra Nevada")
ts <- mo_time_series(mo_wdpa(389011), "NDVI", "Sentinel-2", "2020-01-01", "2021-12-31", step = "monthly")
mo_plot(ts)                                   # ggplot2
write.csv(ts, "ndvi.csv", row.names = FALSE)

zonas <- sf::st_read("zonas.gpkg")
mo_time_series(mo_sf(zonas, "nombre"), "LST", "Landsat", "2015-01-01", "2023-12-31", step = "annual", metric = "max")

capa <- mo_map_layer(mo_wdpa(389011), "NDVI", "Sentinel-2", "2021-01-01", "2021-12-31")
mo_leaflet(capa)                              # leaflet

x <- mo_image(mo_wdpa(389011), "LST", "Modis", "2021-06-01", "2021-08-31", metric = "mean")
rgee::Map$addLayer(x$image, x$vis, x$name)   # rgee
```

Funciones: `mo_init`, `mo_install`, `mo_variables`, `mo_describe`, `mo_protected_areas`, regiones (`mo_wdpa`,
`mo_ecoregion`, `mo_bbox`, `mo_point`, `mo_geojson`, `mo_sf`), `mo_time_series`, `mo_plot`, `mo_map_layer`,
`mo_leaflet`, `mo_image`, `mo_region_stats`, `mo_export_image`, `mo_export_time_series` y `mo_task_status`.

## Catálogo

`src/monitoreo/catalog.json` es el catálogo de la app de MonitorEO, leído (como datos, sin ejecutar JavaScript) del
repositorio de Earth Engine `users/monitoreo-obsnev/monitoreo-obsnev`; guarda el commit de origen. Para actualizarlo
cuando cambie la app:

```bash
python tools/import_catalog.py            # clona el repositorio (credenciales de git de earthengine.googlesource.com)
python tools/import_catalog.py --published   # o desde la app publicada
```

Correcciones respecto a la app, en el código:

- `FIXES` en `catalog.py`: la escala del LAI de MCD15A3H es 0.1, no 0.01.
- La escala y el desplazamiento de las bandas se aplican antes de la fórmula (la app evalúa EVI, el albedo y la
  clorofila de Sentinel-2 sobre las bandas sin escalar).
- Los nombres de banda de las fórmulas se comparan sin mayúsculas (`LST_day_1km` de las entradas 15 y 16).
- Los valores de bandera de MODIS (p. ej. 250 = nube en `NDSI_Snow_Cover`) se descartan siempre.
- Landsat 7 solo se usa hasta el 31-5-2003, como dice el catálogo.
- WDPA cambió su esquema en Earth Engine: el ID es ahora `SITE_ID` (antes `WDPAID`). La app filtra aún por
  `WDPAID` (`modules/selROI`), por lo que su opción de área protegida por ID ya no encuentra nada.

## Desarrollo

```bash
pytest tests/test_offline.py                 # sin Earth Engine
EE_PROJECT=mi-proyecto pytest -m ee          # con Earth Engine
```

Pendiente: elegir la licencia (`r/monitoreo/LICENSE`, `pyproject.toml`). El repositorio es
`github.com/monitoreo-obsnev/monitoreo` (en este README, `qgis/monitoreo_qgis/metadata.txt` y
`r/monitoreo/R/monitoreo.R`); si se publica con otro nombre, hay que cambiarlo ahí.
