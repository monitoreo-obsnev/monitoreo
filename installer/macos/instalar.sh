#!/bin/bash
# Instalador del asistente de MonitorEO para macOS (ver la página Asistente de la wiki). Se pega en el Terminal:
#
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/monitoreo-obsnev/monitoreo/main/installer/macos/instalar.sh)"
#
# (lo que descarga curl no queda en cuarentena, así que macOS no lo bloquea), o se abre con doble clic desde el zip de
# la release, que lo lleva como "Instalar el asistente de MonitorEO.command" (sin firmar: macOS pide permiso).
#
# Instala en ~/MonitorEO/entorno, sin permisos de administrador, el entorno de Python de MonitorEO (Python, Earth
# Engine, GDAL y el paquete monitoreo, del environment.yml del repositorio) con micromamba, que deja en
# ~/MonitorEO/micromamba. Pone en el Escritorio la app "Asistente de MonitorEO", que lo abre en su ventana sin el
# Terminal (sus mensajes van a ~/MonitorEO/assistant-output.log), y la abre. Si el entorno ya existe, solo crea la
# app y la abre; para instalarlo de nuevo, borra ~/MonitorEO/entorno. La app no va firmada, pero la crea este
# ordenador, así que no está en cuarentena y macOS la abre.
# Todo va dentro de main, que se llama al final: una descarga cortada no ejecuta nada.

main() {
	set -euo pipefail
	REPO=https://raw.githubusercontent.com/monitoreo-obsnev/monitoreo/main
	DIR="$HOME/MonitorEO"
	ENV="$DIR/entorno"
	MAMBA_DIR="$DIR/micromamba"
	MAMBA="$MAMBA_DIR/micromamba"
	APP="$HOME/Desktop/Asistente de MonitorEO.app"

	fail() {
		echo
		echo "ERROR: $1"
		echo "Comprueba la conexión a internet y vuelve a abrir el instalador. Si sigue fallando, mira la página"
		echo "Problemas frecuentes de la wiki de MonitorEO."
		read -r -p "Pulsa Intro para cerrar. " _ < /dev/tty || true
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

	rm -f "$HOME/Desktop/Asistente de MonitorEO.command"  # el acceso de las versiones anteriores, en el Terminal
	rm -rf "$APP"
	mkdir -p "$APP/Contents/MacOS"
	cat > "$APP/Contents/Info.plist" <<-EOF
	<?xml version="1.0" encoding="UTF-8"?>
	<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
	<plist version="1.0">
	<dict>
		<key>CFBundleName</key><string>Asistente de MonitorEO</string>
		<key>CFBundleDisplayName</key><string>Asistente de MonitorEO</string>
		<key>CFBundleIdentifier</key><string>es.ugr.monitoreo.asistente</string>
		<key>CFBundleExecutable</key><string>asistente</string>
		<key>CFBundlePackageType</key><string>APPL</string>
		<key>CFBundleVersion</key><string>1</string>
		<key>NSHighResolutionCapable</key><true/>
	</dict>
	</plist>
	EOF
	cat > "$APP/Contents/MacOS/asistente" <<-EOF
	#!/bin/bash
	# Abre el asistente de MonitorEO en su ventana (lo creó su instalador); sus mensajes, a assistant-output.log.
	exec "$ENV/bin/python" -s -m monitoreo.cli assistant >> "$DIR/assistant-output.log" 2>&1
	EOF
	chmod +x "$APP/Contents/MacOS/asistente"

	echo
	echo "Listo. El asistente se abre ahora en su ventana; para cerrarlo, cierra esa ventana."
	echo "Para abrirlo otra vez: doble clic en «Asistente de MonitorEO» del Escritorio. Ya puedes cerrar el Terminal."
	open "$APP"
}

main "$@"
