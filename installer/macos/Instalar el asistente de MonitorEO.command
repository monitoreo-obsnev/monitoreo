#!/bin/bash
# Instalador del asistente de MonitorEO para macOS: se abre con doble clic (ver la página Asistente de la wiki).
#
# Instala en ~/MonitorEO/entorno, sin permisos de administrador, el entorno de Python de MonitorEO (Python, Earth
# Engine, GDAL y el paquete monitoreo, del environment.yml del repositorio) con micromamba, que deja en
# ~/MonitorEO/micromamba. Pone en el Escritorio "Asistente de MonitorEO.command", que lo abre, y lo abre. Si el
# entorno ya existe, solo crea el acceso y abre el asistente; para instalarlo de nuevo, borra ~/MonitorEO/entorno.

set -euo pipefail
REPO=https://raw.githubusercontent.com/monitoreo-obsnev/monitoreo/main
DIR="$HOME/MonitorEO"
ENV="$DIR/entorno"
MAMBA_DIR="$DIR/micromamba"
MAMBA="$MAMBA_DIR/micromamba"
LAUNCHER="$HOME/Desktop/Asistente de MonitorEO.command"

fail() {
	echo
	echo "ERROR: $1"
	echo "Comprueba la conexión a internet y vuelve a abrir el instalador. Si sigue fallando, mira la página"
	echo "Problemas frecuentes de la wiki de MonitorEO."
	read -r -p "Pulsa Intro para cerrar. " _ || true
	exit 1
}
trap 'fail "la instalación se ha parado en la línea $LINENO."' ERR

echo "Instalador del asistente de MonitorEO"
echo "====================================="
echo
echo "Instala en $ENV, sin permisos de administrador, lo que necesita el asistente: Python, Google Earth Engine,"
echo "GDAL y MonitorEO (unos 0,2 GB de descarga y 0,8 GB en disco). Después, al abrirlo por primera vez, el"
echo "asistente descarga su modelo de lenguaje y su motor (unos 5 GB). Las dos descargas son solo la primera vez."
echo

case "$(uname -m)" in
	arm64) PLATFORM=osx-arm64 ;;
	x86_64) PLATFORM=osx-64 ;;
	*) fail "este Mac no es ni Apple Silicon ni Intel ($(uname -m))." ;;
esac

if [ -x "$ENV/bin/monitoreo" ]; then
	echo "El entorno ya está instalado en $ENV."
else
	mkdir -p "$MAMBA_DIR"
	echo "1/3 Descargando micromamba (el instalador de paquetes de conda-forge)..."
	URL="https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-$PLATFORM"
	curl -fL --progress-bar -o "$MAMBA.part" "$URL" || fail "no se ha podido descargar micromamba."
	SHA=$(curl -fsL "$URL.sha256") || fail "no se ha podido descargar la suma de micromamba."
	[ "$(shasum -a 256 "$MAMBA.part" | cut -d' ' -f1)" = "$SHA" ] || fail "la descarga de micromamba está dañada."
	chmod +x "$MAMBA.part"
	mv "$MAMBA.part" "$MAMBA"

	echo "2/3 Descargando la lista de paquetes de MonitorEO..."
	curl -fsL -o "$DIR/environment.yml" "$REPO/environment.yml" || fail "no se ha podido descargar environment.yml."

	echo "3/3 Instalando Python, Earth Engine, GDAL y MonitorEO (unos minutos)..."
	rm -rf "$ENV"
	export MAMBA_ROOT_PREFIX="$MAMBA_DIR" PYTHONNOUSERSITE=1
	"$MAMBA" create -y -p "$ENV" -f "$DIR/environment.yml" || fail "no se ha podido instalar el entorno."
	"$MAMBA" clean -y --all >/dev/null 2>&1 || true  # la caché de los paquetes, ya instalados
	[ -x "$ENV/bin/python" ] && [ -x "$ENV/bin/monitoreo" ] || fail "el entorno no tiene la orden monitoreo."
fi

mkdir -p "$(dirname "$LAUNCHER")"
cat > "$LAUNCHER" <<EOF
#!/bin/bash
# Abre el asistente de MonitorEO (lo creó su instalador). Para cerrarlo, cierra esta ventana.
echo "El asistente de MonitorEO se abre en el navegador. Para cerrarlo, cierra esta ventana."
export PYTHONNOUSERSITE=1
exec "$ENV/bin/python" -m monitoreo.cli assistant
EOF
chmod +x "$LAUNCHER"

echo
echo "Listo. Para abrir el asistente otra vez: doble clic en «Asistente de MonitorEO» del Escritorio."
echo "Ahora se abre en el navegador. Para cerrarlo, cierra esta ventana."
echo
export PYTHONNOUSERSITE=1
exec "$ENV/bin/python" -m monitoreo.cli assistant
