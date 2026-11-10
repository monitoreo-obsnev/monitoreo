#!/bin/bash
# Installer of the MonitorEO assistant for macOS (see the page Assistant of the wiki). It is pasted in the Terminal:
#
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/monitoreo-obsnev/monitoreo/main/installer/macos/instalar.sh)"
#
# (what curl downloads is not quarantined, so macOS does not block it), or opened with a double click from the zip of
# the release, which has it as "Install the MonitorEO assistant.command" (unsigned: macOS asks for permission).
#
# It installs in ~/MonitorEO/entorno, without administrator rights, the Python environment of MonitorEO (Python,
# Earth Engine, GDAL and the package monitoreo, from the environment.yml of the repository) with micromamba, which it
# leaves in ~/MonitorEO/micromamba. It puts on the Desktop the app "MonitorEO Assistant" (with the logo of MonitorEO,
# installer/icons/monitoreo-assistant.icns), which opens the assistant in its window without the Terminal (its
# messages go to ~/MonitorEO/assistant-output.log), and opens it. If the environment already exists, it only
# creates the app and opens it; to install it again, delete ~/MonitorEO/entorno
# (the folder keeps its Spanish name, "environment", so that existing installations are found). The app is not
# signed, but this computer creates it, so it is not quarantined and macOS opens it.
# It downloads no language model: the assistant uses, by default, the model of MonitorEO in the cloud; a model of
# Ollama is optional, and the assistant downloads it (monitoreo.engine) if the user chooses one in Settings.
# Everything is inside main, which is called at the end: a broken download runs nothing.

main() {
	set -euo pipefail
	REPO=https://raw.githubusercontent.com/monitoreo-obsnev/monitoreo/main
	DIR="$HOME/MonitorEO"
	ENV="$DIR/entorno"
	MAMBA_DIR="$DIR/micromamba"
	MAMBA="$MAMBA_DIR/micromamba"
	APP="$HOME/Desktop/MonitorEO Assistant.app"

	fail() {  # fail MESSAGE [LINES OF WHAT TO DO]: by default, the connection, the cause of almost every error
		echo
		echo "ERROR: $1"
		if [ $# -gt 1 ]; then
			printf '%s\n' "${@:2}"
		else
			echo "Check the internet connection and open the installer again. If it keeps failing, see the page"
			echo "Troubleshooting of the wiki of MonitorEO."
		fi
		read -r -p "Press Enter to close. " _ < /dev/tty || true
		exit 1
	}
	trap 'fail "the installation stopped at line $LINENO."' ERR

	echo "Installer of the MonitorEO assistant"
	echo "===================================="
	echo
	echo "It installs in $ENV, without administrator rights, what the assistant needs: Python, Google Earth Engine,"
	echo "GDAL and MonitorEO (about 0.2 GB to download and 0.8 GB on disk, only the first time). The assistant uses the"
	echo "language model of MonitorEO, in the cloud, with nothing more to download. A model on this computer (Ollama) is"
	echo "optional: if you choose one in Settings, it downloads about 5 GB the first time."
	echo

	case "$(uname -m)" in
		arm64) PLATFORM=osx-arm64 ;;
		x86_64) PLATFORM=osx-64 ;;
		*) fail "this Mac is neither Apple Silicon nor Intel ($(uname -m))." ;;
	esac

	# The app goes on the Desktop, and macOS asks whether the Terminal may access it (once). If the user said Don't
	# Allow, every access fails with "Operation not permitted" and macOS does not ask again: say so now, before the
	# downloads, instead of blaming the connection at the end.
	TEST="$HOME/Desktop/.monitoreo-installer-test"
	if ! { mkdir -p "$HOME/Desktop" && touch "$TEST" && rm -f "$TEST"; } 2>/dev/null; then
		fail "the Terminal may not access the Desktop, where the installer leaves the app of the assistant." \
			"Go to System Settings > Privacy & Security > Files & Folders > Terminal, turn on Desktop and open the" \
			"installer again."
	fi

	if [ -x "$ENV/bin/monitoreo" ]; then
		echo "The environment is already installed in $ENV."
	else
		mkdir -p "$MAMBA_DIR"
		echo "1/3 Downloading micromamba (the package installer of conda-forge)..."
		URL="https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-$PLATFORM"
		curl -fL --progress-bar -o "$MAMBA.part" "$URL" || fail "micromamba could not be downloaded."
		SHA=$(curl -fsL "$URL.sha256") || fail "the checksum of micromamba could not be downloaded."
		[ "$(shasum -a 256 "$MAMBA.part" | cut -d' ' -f1)" = "$SHA" ] || fail "the download of micromamba is damaged."
		chmod +x "$MAMBA.part"
		mv "$MAMBA.part" "$MAMBA"

		echo "2/3 Downloading the list of packages of MonitorEO..."
		curl -fsL -o "$DIR/environment.yml" "$REPO/environment.yml" || fail "environment.yml could not be downloaded."

		echo "3/3 Installing Python, Earth Engine, GDAL and MonitorEO (a few minutes)..."
		rm -rf "$ENV"
		export MAMBA_ROOT_PREFIX="$MAMBA_DIR" PYTHONNOUSERSITE=1
		"$MAMBA" create -y -p "$ENV" -f "$DIR/environment.yml" || fail "the environment could not be installed."
		"$MAMBA" clean -y --all >/dev/null 2>&1 || true  # the cache of the packages, already installed
		[ -x "$ENV/bin/python" ] && [ -x "$ENV/bin/monitoreo" ] || fail "the environment has no command monitoreo."
	fi

	rm -f "$HOME/Desktop/Asistente de MonitorEO.command"  # the shortcut of old versions, in the Terminal
	rm -rf "$HOME/Desktop/Asistente de MonitorEO.app"  # the app of the versions with Spanish texts
	rm -rf "$APP"
	mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
	# its icon, the logo of MonitorEO (without it, the generic one of the apps)
	curl -fsL -o "$APP/Contents/Resources/monitoreo-assistant.icns" "$REPO/installer/icons/monitoreo-assistant.icns" ||
		rm -f "$APP/Contents/Resources/monitoreo-assistant.icns"
	cat > "$APP/Contents/Info.plist" <<-EOF
	<?xml version="1.0" encoding="UTF-8"?>
	<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
	<plist version="1.0">
	<dict>
		<key>CFBundleName</key><string>MonitorEO Assistant</string>
		<key>CFBundleDisplayName</key><string>MonitorEO Assistant</string>
		<key>CFBundleIdentifier</key><string>es.ugr.monitoreo.asistente</string>
		<key>CFBundleExecutable</key><string>asistente</string>
		<key>CFBundleIconFile</key><string>monitoreo-assistant</string>
		<key>CFBundlePackageType</key><string>APPL</string>
		<key>CFBundleVersion</key><string>1</string>
		<key>NSHighResolutionCapable</key><true/>
	</dict>
	</plist>
	EOF
	cat > "$APP/Contents/MacOS/asistente" <<-EOF
	#!/bin/bash
	# Opens the MonitorEO assistant in its window (created by its installer); its messages go to assistant-output.log.
	exec "$ENV/bin/python" -s -m monitoreo.cli assistant >> "$DIR/assistant-output.log" 2>&1
	EOF
	chmod +x "$APP/Contents/MacOS/asistente"

	echo
	echo "Done. The assistant opens now in its window; to close it, close that window."
	echo "To open it again: double click «MonitorEO Assistant» on the Desktop. You can close the Terminal now."
	open "$APP"
}

main "$@"
