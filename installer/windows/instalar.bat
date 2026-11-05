@echo off
rem Installer of the MonitorEO assistant for Windows (see the page Assistant of the wiki): it opens with a double
rem click from the zip of the release, which has it as "Install the MonitorEO assistant.bat" (unsigned: Windows may
rem warn), or it is downloaded and opened with a command in the Command Prompt (what curl downloads has no mark of
rem the Internet, so SmartScreen does not stop it):
rem
rem   curl -fsSLo "%TEMP%\instalar-monitoreo.bat" https://raw.githubusercontent.com/monitoreo-obsnev/monitoreo/main/installer/windows/instalar.bat && "%TEMP%\instalar-monitoreo.bat"
rem
rem It installs in %USERPROFILE%\MonitorEO\entorno, without administrator rights, the Python environment of
rem MonitorEO (Python, Earth Engine, GDAL and the package monitoreo, from the environment.yml of the repository) with
rem micromamba, which it leaves in %USERPROFILE%\MonitorEO\micromamba. It puts on the Desktop the shortcut
rem "MonitorEO Assistant", which opens the assistant in its window with pythonw.exe, without a console (its messages
rem go to %USERPROFILE%\MonitorEO\assistant-output.log), and opens it. If the environment already exists, it only
rem creates the shortcut and opens the assistant; to install it again, delete the folder entorno (it keeps its
rem Spanish name, "environment", so that existing installations are found). No accents: cmd reads this file with the
rem code page of the console.
setlocal
title Installer of the MonitorEO assistant
set "REPO=https://raw.githubusercontent.com/monitoreo-obsnev/monitoreo/main"
set "DIR=%USERPROFILE%\MonitorEO"
set "ENV=%DIR%\entorno"
set "MAMBA_DIR=%DIR%\micromamba"
set "MAMBA=%MAMBA_DIR%\micromamba.exe"
set "PYTHONNOUSERSITE=1"

echo Installer of the MonitorEO assistant
echo ====================================
echo.
echo It installs in %ENV%, without administrator rights, what the assistant needs:
echo Python, Google Earth Engine, GDAL and MonitorEO (about 0.2 GB to download and 1 GB on disk). Then, the first
echo time it opens, the assistant downloads its language model and its engine (about 7 GB). Both downloads happen
echo only the first time.
echo.

if exist "%ENV%\python.exe" if exist "%ENV%\Scripts\monitoreo.exe" (
  echo The environment is already installed in %ENV%.
  goto :launcher
)
if not exist "%MAMBA_DIR%" mkdir "%MAMBA_DIR%"
echo 1/3 Downloading micromamba (the package installer of conda-forge)...
set "URL=https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-win-64"
curl -fL --progress-bar -o "%MAMBA%.part" "%URL%" || goto :fail
curl -fsL -o "%MAMBA%.sha256" "%URL%.sha256" || goto :fail
powershell -NoProfile -Command "if ((Get-FileHash -Algorithm SHA256 -LiteralPath ($env:MAMBA + '.part')).Hash -ne (Get-Content -Raw -LiteralPath ($env:MAMBA + '.sha256')).Trim()) { exit 1 }" || goto :damaged
move /y "%MAMBA%.part" "%MAMBA%" >nul || goto :fail

echo 2/3 Downloading the list of packages of MonitorEO...
curl -fsL -o "%DIR%\environment.yml" "%REPO%/environment.yml" || goto :fail

echo 3/3 Installing Python, Earth Engine, GDAL and MonitorEO (a few minutes)...
if exist "%ENV%" rmdir /s /q "%ENV%"
set "MAMBA_ROOT_PREFIX=%MAMBA_DIR%"
"%MAMBA%" create -y -p "%ENV%" -f "%DIR%\environment.yml" || goto :fail
"%MAMBA%" clean -y --all >nul 2>&1
if not exist "%ENV%\Scripts\monitoreo.exe" goto :fail

:launcher
rem the shortcut of old versions opened a console with this .bat; the next ones had Spanish names
if exist "%DIR%\Asistente de MonitorEO.bat" del "%DIR%\Asistente de MonitorEO.bat"
powershell -NoProfile -Command "$p = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Asistente de MonitorEO.lnk'; if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p }"
powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'MonitorEO Assistant.lnk')); $s.TargetPath = Join-Path $env:ENV 'pythonw.exe'; $s.Arguments = '-s -m monitoreo.cli assistant'; $s.WorkingDirectory = $env:DIR; $s.IconLocation = (Join-Path $env:ENV 'python.exe') + ',0'; $s.Save()"

echo.
echo Done. The assistant opens now in its window; to close it, close that window.
echo To open it again: double click "MonitorEO Assistant" on the Desktop. You can close this window now.
start "" "%ENV%\pythonw.exe" -s -m monitoreo.cli assistant
exit /b

:damaged
echo.
echo ERROR: the download of micromamba is damaged.
:fail
echo.
echo ERROR: the installation did not finish. Check the internet connection and open the installer again.
echo If it keeps failing, see the page Troubleshooting of the wiki of MonitorEO.
pause
exit /b 1
