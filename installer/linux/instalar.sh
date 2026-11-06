#!/bin/bash
# Installer of the MonitorEO assistant for Ubuntu (the LTS versions 22.04, 24.04 and 26.04, on PCs and on ARM; see
# the page Assistant of the wiki). It is pasted in the Terminal (Ctrl+Alt+T); Ubuntu has wget, but not always curl:
#
#   bash -c "$(wget -qO- https://raw.githubusercontent.com/monitoreo-obsnev/monitoreo/main/installer/linux/instalar.sh)"
#
# It installs in ~/MonitorEO/entorno, without administrator rights, the Python environment of MonitorEO (Python,
# Earth Engine, GDAL and the package monitoreo, from the environment.yml of the repository) with micromamba, which it
# leaves in ~/MonitorEO/micromamba. On Linux, the window of the assistant (pywebview) needs Qt WebEngine, which is
# not in environment.yml (the same for every system): it adds PyQt6-WebEngine of conda-forge. It writes the launcher
# entorno/bin/monitoreo-assistant, which opens the assistant in its window without the Terminal (its messages go to
# ~/MonitorEO/assistant-output.log), puts "MonitorEO Assistant" in the applications (Activities) and on the Desktop,
# and opens it. If the environment already exists, it only adds what is missing,
# writes the launchers and opens it; to install it again, delete ~/MonitorEO/entorno (the folder keeps its Spanish
# name, "environment", as on macOS and Windows). Other Linux distributions with glibc 2.28 or later may work too.
# Everything is inside main, which is called at the end: a broken download runs nothing.

main() {
	set -euo pipefail
	REPO=https://raw.githubusercontent.com/monitoreo-obsnev/monitoreo/main
	DIR="$HOME/MonitorEO"
	ENV="$DIR/entorno"
	MAMBA_DIR="$DIR/micromamba"
	MAMBA="$MAMBA_DIR/micromamba"
	LAUNCHER="$ENV/bin/monitoreo-assistant"
	APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
	ICON="${XDG_DATA_HOME:-$HOME/.local/share}/icons/monitoreo-assistant.png"
	ENTRY=monitoreo-assistant.desktop
	WINDOW="pyqt6-webengine qtpy"  # the window of the assistant: Qt WebEngine, which pywebview reaches through QtPy
	export MAMBA_ROOT_PREFIX="$MAMBA_DIR" PYTHONNOUSERSITE=1

	fail() {
		echo
		echo "ERROR: $1"
		echo "Check the internet connection and run the installer again. If it keeps failing, see the page"
		echo "Troubleshooting of the wiki of MonitorEO."
		exit 1
	}
	trap 'fail "the installation stopped at line $LINENO."' ERR

	download() {  # download URL FILE: with curl if there is one, else with wget (Ubuntu has it always)
		if command -v curl >/dev/null 2>&1; then
			curl -fsSL -o "$2" "$1"
		elif command -v wget >/dev/null 2>&1; then
			wget -q -O "$2" "$1"
		else
			fail "this computer has neither wget nor curl: install one (sudo apt install wget) and run it again."
		fi
	}

	echo "Installer of the MonitorEO assistant"
	echo "===================================="
	echo
	echo "It installs in $ENV, without administrator rights, what the assistant needs: Python, Google Earth Engine,"
	echo "GDAL, MonitorEO and its window (about 0.6 GB to download and 2.5 GB on disk, only the first time). The"
	echo "assistant uses the language model of MonitorEO, in the cloud, with nothing more to download."
	echo

	[ "$(id -u)" != 0 ] || fail "run the installer as your user, without sudo: it installs everything in your folder."
	case "$(uname -m)" in
		x86_64) PLATFORM=linux-64 ;;
		aarch64 | arm64) PLATFORM=linux-aarch64 ;;
		*) fail "this computer is neither a PC (x86_64) nor ARM (aarch64): $(uname -m)." ;;
	esac
	# shellcheck source=/dev/null
	SYSTEM=$( (. /etc/os-release && echo "$ID $VERSION_ID|$PRETTY_NAME") 2>/dev/null || echo "|$(uname -s)")
	case "${SYSTEM%%|*}" in
		"ubuntu 22.04" | "ubuntu 24.04" | "ubuntu 26.04") ;;
		*) echo "Note: this is ${SYSTEM#*|}; the installer is made for Ubuntu 22.04, 24.04 and 26.04 LTS, but it may work."
		   echo ;;
	esac

	window() {  # whether the window of the assistant (pywebview with Qt WebEngine) loads in the environment
		QT_API=pyqt6 "$ENV/bin/python" -s -c 'import webview, qtpy.QtWebEngineWidgets' >/dev/null 2>&1
	}

	if [ -x "$ENV/bin/python" ] && [ -x "$ENV/bin/monitoreo" ]; then
		echo "The environment is already installed in $ENV."
		if ! window; then
			[ -x "$MAMBA" ] || fail "$MAMBA is missing: delete $ENV and run the installer again."
			echo "Adding the window of the assistant (Qt WebEngine)..."
			# shellcheck disable=SC2086  # WINDOW: two packages
			"$MAMBA" install -y -p "$ENV" -c conda-forge --override-channels $WINDOW || fail "Qt WebEngine could not be installed."
			"$MAMBA" clean -y --all >/dev/null 2>&1 || true
		fi
	else
		mkdir -p "$MAMBA_DIR"
		echo "1/3 Downloading micromamba (the package installer of conda-forge, 15 MB)..."
		URL="https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-$PLATFORM"
		download "$URL" "$MAMBA.part" || fail "micromamba could not be downloaded."
		download "$URL.sha256" "$MAMBA.sha256" || fail "the checksum of micromamba could not be downloaded."
		[ "$(sha256sum "$MAMBA.part" | cut -d' ' -f1)" = "$(tr -d '[:space:]' < "$MAMBA.sha256")" ] ||
			fail "the download of micromamba is damaged."
		chmod +x "$MAMBA.part"
		mv "$MAMBA.part" "$MAMBA"
		rm -f "$MAMBA.sha256"

		echo "2/3 Downloading the list of packages of MonitorEO..."
		download "$REPO/environment.yml" "$DIR/environment.yml" || fail "environment.yml could not be downloaded."

		echo "3/3 Installing Python, Earth Engine, GDAL, MonitorEO and its window (a few minutes)..."
		rm -rf "$ENV"
		# shellcheck disable=SC2086  # WINDOW: two packages, solved with those of environment.yml
		"$MAMBA" create -y -p "$ENV" -f "$DIR/environment.yml" $WINDOW || fail "the environment could not be installed."
		"$MAMBA" clean -y --all >/dev/null 2>&1 || true  # the cache of the packages, already installed
		[ -x "$ENV/bin/python" ] && [ -x "$ENV/bin/monitoreo" ] || fail "the environment has no command monitoreo."
	fi
	if ! window; then
		echo "Note: the window of the assistant (Qt WebEngine) does not load on this computer: the assistant opens in"
		echo "the browser instead. See the page Troubleshooting of the wiki of MonitorEO."
	fi

	# the launcher: the settings of the window, then the assistant, with its messages in assistant-output.log
	cat > "$LAUNCHER" <<-EOF
	#!/bin/bash
	# Opens the MonitorEO assistant in its window (written by its installer); its messages go to assistant-output.log.
	# The window is Qt WebEngine (PyQt6, through QtPy), through X11 (XWayland in a Wayland session), with the name of
	# this launcher (so Ubuntu shows it with its icon); the charts are drawn without a window (Agg).
	export QT_API=pyqt6 PYWEBVIEW_GUI=qt MPLBACKEND=Agg RESOURCE_NAME=monitoreo-assistant
	[ -z "\${DISPLAY:-}" ] || export QT_QPA_PLATFORM=xcb
	# Qt WebEngine looks for the system bus of D-Bus in the environment: that of the system
	[ ! -S /run/dbus/system_bus_socket ] || export DBUS_SYSTEM_BUS_ADDRESS=unix:path=/run/dbus/system_bus_socket
	# Without the sandbox of Chromium (that of Qt WebEngine), with which the page may stay blank: its filter of system
	# calls (seccomp) kills it with recent kernels and glibc (SIGSYS), and Ubuntu 24.04 and later give the user
	# namespaces that it needs only to the programs with a profile of AppArmor. The window shows only the page of the
	# assistant on this computer; the links to other pages open in the browser.
	export QTWEBENGINE_DISABLE_SANDBOX=1
	exec "$ENV/bin/python" -s -m monitoreo.cli assistant "\$@" >> "$DIR/assistant-output.log" 2>&1
	EOF
	chmod +x "$LAUNCHER"

	# "MonitorEO Assistant" in the applications and on the Desktop (Exec: the path between quotes, for the spaces)
	mkdir -p "$APPS" "$(dirname "$ICON")"
	download "$REPO/qgis/monitoreo_qgis/icon.png" "$ICON" || rm -f "$ICON"  # without icon, the generic one
	cat > "$APPS/$ENTRY" <<-EOF
	[Desktop Entry]
	Type=Application
	Name=MonitorEO Assistant
	GenericName=Monitoring of ecosystems with satellites
	Comment=Maps, charts and reports of Essential Biodiversity Variables with Google Earth Engine
	Exec="$LAUNCHER"
	Icon=$([ -f "$ICON" ] && echo "$ICON" || echo applications-science)
	Terminal=false
	Categories=Science;Geography;
	Keywords=MonitorEO;OBSNEV;Earth Engine;NDVI;satellite;biodiversity;
	StartupNotify=true
	StartupWMClass=monitoreo-assistant
	EOF
	chmod +x "$APPS/$ENTRY"
	DESKTOP=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
	if [ -d "$DESKTOP" ] && [ "$DESKTOP" != "$HOME" ]; then
		cp "$APPS/$ENTRY" "$DESKTOP/$ENTRY"
		chmod +x "$DESKTOP/$ENTRY"
		# the icons of the Desktop of Ubuntu open a launcher only if it is trusted («Allow Launching»)
		gio set "$DESKTOP/$ENTRY" metadata::trusted true >/dev/null 2>&1 || true
	fi

	echo
	if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
		echo "Done. The assistant opens now in its window; to close it, close that window."
		echo "To open it again: «MonitorEO Assistant» on the Desktop or in the applications (press the Super key and"
		echo "type MonitorEO). You can close the Terminal now."
		# in a session of its own: closing the Terminal leaves it open
		setsid -f "$LAUNCHER" >/dev/null 2>&1 < /dev/null || echo "(It did not open: open it from the applications.)"
	else
		echo "Done. Open the assistant with «MonitorEO Assistant» on the Desktop or in the applications (press the"
		echo "Super key and type MonitorEO), or with: $LAUNCHER"
	fi
}

main "$@"
