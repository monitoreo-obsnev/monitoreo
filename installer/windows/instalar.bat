@echo off
rem Installer of the MonitorEO assistant for Windows (see the page Assistant of the wiki): it opens with a double
rem click from the zip of the release, which has it as "Install the MonitorEO assistant.bat" (unsigned: Windows may
rem warn), or it is downloaded and opened with a command in the Command Prompt (what curl downloads has no mark of
rem the Internet, so SmartScreen does not stop it):
rem
rem   curl -fsSLo "%TEMP%\instalar-monitoreo.bat" https://raw.githubusercontent.com/monitoreo-obsnev/monitoreo/main/installer/windows/instalar.bat && "%TEMP%\instalar-monitoreo.bat"
rem
rem It installs in %USERPROFILE%\MonitorEO\entorno, without administrator rights, the Python environment of MonitorEO
rem (Python, Earth Engine, GDAL and the package monitoreo, from the environment.yml of the repository) with
rem micromamba, which it leaves in %USERPROFILE%\MonitorEO\micromamba (with the runtime of Visual C++ that it needs,
rem if Windows does not have it; while it installs, the packages are in %SystemDrive%\MonitorEO-pkgs, a short path).
rem It puts on the Desktop the shortcut "MonitorEO Assistant" (with the logo of MonitorEO,
rem installer/icons/monitoreo-assistant.ico), which opens the assistant in its window with pythonw.exe, without a
rem console (its messages go to %USERPROFILE%\MonitorEO\assistant-output.log), and opens it. If the environment
rem already exists, it only creates the shortcut and opens the assistant; to install it again, delete the folder
rem entorno (it keeps its Spanish name, "environment", so that existing installations are found). No accents: cmd
rem reads this file with the code page of the console.
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
echo Python, Google Earth Engine, GDAL and MonitorEO (about 0.3 GB to download and 1.7 GB on disk). Then, the first
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
rem micromamba needs the runtime of Visual C++ (MSVCP140.dll, VCRUNTIME140.dll...), which a new Windows does not
rem have: then it gets its DLLs from the package vc14_runtime of conda-forge
"%MAMBA%" --version >nul 2>&1 || call :vcruntime || goto :novcruntime

echo 2/3 Downloading the list of packages of MonitorEO...
curl -fsL -o "%DIR%\environment.yml" "%REPO%/environment.yml" || goto :fail

echo 3/3 Installing Python, Earth Engine, GDAL and MonitorEO (a few minutes)...
if exist "%ENV%" rmdir /s /q "%ENV%"
set "MAMBA_ROOT_PREFIX=%MAMBA_DIR%"
rem the packages, while they are installed, in a short folder: micromamba keeps them under the address of their
rem channel (pkgs\https\conda.anaconda.org\conda-forge\win-64\...), and in the folder of the user some of their
rem files would pass the 260 characters of a path of Windows (its long paths need an administrator)
set "CONDA_PKGS_DIRS=%SystemDrive%\MonitorEO-pkgs"
if not exist "%CONDA_PKGS_DIRS%" mkdir "%CONDA_PKGS_DIRS%" 2>nul || set "CONDA_PKGS_DIRS=%MAMBA_DIR%\pkgs"
"%MAMBA%" create -y -p "%ENV%" -f "%DIR%\environment.yml" || goto :fail
"%MAMBA%" clean -y --all >nul 2>&1
if exist "%SystemDrive%\MonitorEO-pkgs" rmdir /s /q "%SystemDrive%\MonitorEO-pkgs" >nul 2>&1
rem the cache of earlier versions of this installer (of an installation that failed)
if exist "%MAMBA_DIR%\pkgs" rmdir /s /q "%MAMBA_DIR%\pkgs" >nul 2>&1
if not exist "%ENV%\Scripts\monitoreo.exe" goto :fail

:launcher
rem the shortcut of old versions opened a console with this .bat; the next ones had Spanish names
if exist "%DIR%\Asistente de MonitorEO.bat" del "%DIR%\Asistente de MonitorEO.bat"
powershell -NoProfile -Command "$p = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Asistente de MonitorEO.lnk'; if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p }"
rem its icon, the logo of MonitorEO (without it, that of Python)
curl -fsL -o "%ENV%\monitoreo-assistant.ico" "%REPO%/installer/icons/monitoreo-assistant.ico" || del "%ENV%\monitoreo-assistant.ico" >nul 2>&1
powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'MonitorEO Assistant.lnk')); $s.TargetPath = Join-Path $env:ENV 'pythonw.exe'; $s.Arguments = '-s -m monitoreo.cli assistant'; $s.WorkingDirectory = $env:DIR; $ico = Join-Path $env:ENV 'monitoreo-assistant.ico'; if (-not (Test-Path -LiteralPath $ico)) { $ico = Join-Path $env:ENV 'python.exe' }; $s.IconLocation = $ico + ',0'; $s.Save()"

echo.
echo Done. The assistant opens now in its window; to close it, close that window.
echo To open it again: double click "MonitorEO Assistant" on the Desktop. You can close this window now.
start "" "%ENV%\pythonw.exe" -s -m monitoreo.cli assistant
exit /b

:vcruntime
rem the DLLs of the runtime of Visual C++ next to micromamba.exe, without installing anything in Windows (as an app
rem may have them): from the package vc14_runtime of conda-forge (a .conda: a zip with a .tar.zst, which the tar of
rem Windows 11 opens), only if Microsoft signs them
echo     Adding the runtime of Visual C++ of Microsoft, which micromamba needs...
set "VC=%MAMBA_DIR%\vc14_runtime"
if exist "%VC%" rmdir /s /q "%VC%"
mkdir "%VC%" || exit /b 1
curl -fsSL -o "%VC%\vc14_runtime.conda" "https://conda.anaconda.org/conda-forge/win-64/vc14_runtime-14.51.36247-habf1de7_42.conda" || exit /b 1
tar -xf "%VC%\vc14_runtime.conda" -C "%VC%" || exit /b 1
for %%f in ("%VC%\pkg-*.tar.zst") do tar -xf "%%~f" -C "%VC%" || exit /b 1
powershell -NoProfile -Command "$n = 0; foreach ($f in Get-ChildItem -LiteralPath $env:VC -Filter *.dll) { $s = Get-AuthenticodeSignature -LiteralPath $f.FullName; if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { exit 1 }; Copy-Item -LiteralPath $f.FullName -Destination $env:MAMBA_DIR -Force; $n++ }; if ($n -eq 0) { exit 1 }" || exit /b 1
rmdir /s /q "%VC%"
"%MAMBA%" --version >nul 2>&1 || exit /b 1
exit /b 0

:novcruntime
echo.
echo ERROR: micromamba needs the runtime of Visual C++ of Microsoft, which this computer does not have and the
echo installer could not add. Install it from https://aka.ms/vs/17/release/vc_redist.x64.exe (it asks for an
echo administrator) and open the installer again.
pause
exit /b 1

:damaged
echo.
echo ERROR: the download of micromamba is damaged.
:fail
echo.
echo ERROR: the installation did not finish. Check the internet connection and open the installer again.
echo If it keeps failing, see the page Troubleshooting of the wiki of MonitorEO.
pause
exit /b 1
